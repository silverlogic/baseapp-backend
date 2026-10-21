# BaseApp PDF Generation

Reusable Django app for PDF generation and rendering. It drives a headless **Google Chrome** (or Chromium) to print to PDF, so you can render any webpage, local HTML file, HTML string, or template (Django or Jinja2) with full CSS support.

`baseapp_pdf` follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin so it participates in `INSTALLED_APPS` aggregation. It's a pure utility package — no models, migrations, URLs, or GraphQL — so there's nothing else to wire.

## Features

- Render URLs to PDF
- Render local HTML files to PDF
- Render HTML strings to PDF bytes
- Render Django or Jinja2 templates to PDF
- Configurable Chrome binary, timeout and arguments
- Optional DRF renderer for `application/pdf` responses
- Management commands for PDF generation
- Example template with invoice-like formatting

## Requirements

The rendering engine is **Google Chrome** invoked as `google-chrome` (headless), or whichever binary `BASEAPP_PDF_CHROME_BINARY` names. It must be installed and on `PATH` (or given as an absolute path) in the environment that runs the rendering (the project's dev/CI images already provide it). When it's missing, the utilities raise `BaseAppBackendPDFChromeNotInstalledException`; use `chrome_available()` to check first and degrade instead.

**arm64 images (Apple Silicon, Graviton):** Google does not publish Chrome for Linux arm64, so the `google-chrome-stable` package only installs on amd64. Install Debian's `chromium` package (plus fonts, e.g. `fonts-liberation`) instead, and point the package at it:

```python
BASEAPP_PDF_CHROME_BINARY = "chromium"
```

Symlinking `chromium` to `google-chrome` works too and needs no setting.

## How to install

Install the package with `pip install baseapp-backend[pdf]`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

Add `baseapp_pdf` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_pdf",
    # ...
]
```

### Settings

All optional; they are read on every render, so `override_settings` works in tests.

| Setting | Default | |
| --- | --- | --- |
| `BASEAPP_PDF_CHROME_BINARY` | `"google-chrome"` | Executable to run, e.g. `"chromium"` or an absolute path. |
| `BASEAPP_PDF_TIMEOUT` | `60` | Seconds a Chrome call may take before it is killed and `BaseAppBackendPDFRenderToPDFException` is raised. `None` waits forever. |
| `BASEAPP_PDF_EXTRA_ARGS` | `()` | Chrome arguments added to every render, e.g. `["--font-render-hinting=none"]`. |
| `BASEAPP_PDF_NO_SANDBOX` | `True` | Pass `--no-sandbox`, which Chrome needs when it runs as root in a container. Set `False` where Chrome's sandbox can work. |

## How to use

### In your code

When you only need the bytes (to store in a `FileField`, attach to an email or return from a view), use the bytes helpers in `baseapp_pdf.utils`:

```python
from baseapp_pdf.utils import render_html_to_pdf, render_template_to_pdf_bytes

# An HTML string.
pdf_bytes = render_html_to_pdf("<h1>Invoice 42</h1>")

# Relative URLs (images, stylesheets, fonts) need somewhere to resolve against.
pdf_bytes = render_html_to_pdf(html, base_url="https://example.com/static/")  # or "file:///app/static/"

# A template name, looked up in every configured engine, or a template object from any
# engine (Django, Jinja2, anything with `render(context)`), plus its context.
pdf_bytes = render_template_to_pdf_bytes("pdfs/invoice.html", {"invoice": invoice})
pdf_bytes = render_template_to_pdf_bytes(jinja_env.get_template("invoice.html.j2"), context)
```

`base_url` is inserted as the first `<base>` element of the document, so it wins over one the HTML already has. Without it, relative URLs resolve against the private temporary folder the HTML is written to, where nothing else exists. The HTML is written as UTF-8, so non-ASCII text renders correctly with or without `<meta charset>`.

The original helpers are **context managers** that yield a `Path` to a temporary PDF; the file (and Chrome's scratch files) are cleaned up on exit, so read the bytes inside the `with` block:

```python
from baseapp_pdf.utils import render_to_pdf, render_template_to_pdf

# A local HTML file path or a URL string.
with render_to_pdf(source="path/to/file.html") as pdf_file:      # or source="https://example.com"
    pdf_bytes = pdf_file.read_bytes()

# A template name (or a template object from any engine) + context.
context = {"pdf_title": "My PDF", "pdf_margins": "1cm 1cm"}       # plus your template variables
with render_template_to_pdf(source="pdfs/my-template.html", context=context) as pdf_file:
    pdf_bytes = pdf_file.read_bytes()
```

Every helper also takes `extra_args`, Chrome arguments for that one render (added after `BASEAPP_PDF_EXTRA_ARGS`), and `render_template_to_pdf` takes `base_url` like the bytes helpers. `render_template_to_html(source, context)` returns the rendered HTML without printing it, which is handy for previews and tests.

Each render runs in its own private temporary directory, which holds the HTML, the PDF, Chrome's profile (`--user-data-dir`) and Chrome's scratch files, and which is removed when the render ends, so concurrent renders (threads, Celery workers) never touch each other's files.

To render only when Chrome is there, and skip or fall back otherwise:

```python
from baseapp_pdf.utils import chrome_available

if chrome_available():
    document.pdf.save("document.pdf", ContentFile(render_html_to_pdf(html)))
```

Output is validated before being yielded: an empty file, or one whose text contains Chrome render errors (`ERR_FILE_NOT_FOUND` for a missing local file, `DNS_PROBE_FINISHED_NXDOMAIN` for an unresolvable URL), raises `BaseAppBackendPDFRenderToPDFException`. A render that exceeds `BASEAPP_PDF_TIMEOUT`, or that Chrome exits non-zero on, raises the same exception. All exceptions derive from `BaseAppBackendPDFException` (`baseapp_pdf.exceptions`).

### In a DRF view

`baseapp_pdf.rest_framework.renderers.PDFRenderer` (media type `application/pdf`, format `pdf`) lets a view answer `Accept: application/pdf` or `?format=pdf`. Return the PDF bytes in the `Response`; they pass through unchanged. Anything else, such as the payload of an error response, is rendered as JSON with an `application/json` content type.

```python
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from baseapp_pdf.rest_framework.renderers import PDFRenderer
from baseapp_pdf.utils import render_template_to_pdf_bytes


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    @action(detail=True, renderer_classes=[PDFRenderer])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        pdf_bytes = render_template_to_pdf_bytes("pdfs/invoice.html", {"invoice": invoice})
        return Response(
            pdf_bytes,
            headers={"Content-Disposition": f'attachment; filename="invoice-{invoice.pk}.pdf"'},
        )
```

Rendering takes a second or more, so for documents that are downloaded repeatedly, render once (e.g. in a Celery task), store the bytes and serve the stored file.

### Management commands

Render a local HTML file or URL to a PDF written into a destination directory (defaults to the cwd):

```bash
python manage.py render_to_pdf --source path/to/file.html --destination /path/to/output/dir
# or
python manage.py render_to_pdf --source https://example.com --destination /path/to/output/dir
```

Generate a PDF from the bundled example template:

```bash
python manage.py render_example_template_to_pdf --destination /path/to/output/dir
```

## Example template

The package bundles [`templates/pdfs/render-template-to-pdf-example.html`](templates/pdfs/render-template-to-pdf-example.html), an invoice-like layout demonstrating custom headers/footers, tables, and dynamic content. `render_example_template_to_pdf` renders it with sample context — use it as a starting point for your own templates.

## Testing

The package's own tests mock Chrome (`baseapp_pdf/tests/unit`), and the tests that print real PDFs (`baseapp_pdf/tests/integration`) are skipped where `chrome_available()` is `False`. In your project, do the same: patch `baseapp_pdf.utils.subprocess.run`, or mark real renders with `pytest.mark.skipif(not chrome_available(), ...)`.

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).
