# BaseApp PDF Generation

Reusable Django app for PDF generation and rendering. It drives a headless **Google Chrome** to print to PDF, so you can render any webpage, local HTML file, or Django template with full CSS support.

`baseapp_pdf` follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin so it participates in `INSTALLED_APPS` aggregation. It's a pure utility package — no models, migrations, URLs, or GraphQL — so there's nothing else to wire.

## Features

- Render URLs to PDF
- Render local HTML files to PDF
- Render Django templates to PDF
- Management commands for PDF generation
- Example template with invoice-like formatting

## Requirements

The rendering engine is **Google Chrome** invoked as `google-chrome` (headless). It must be installed and on `PATH` in the environment that runs the rendering (the project's dev/CI images already provide it). When it's missing, the utilities raise `BaseAppBackendPDFChromeNotInstalledException`.

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

## How to use

### In your code

The two helpers in `baseapp_pdf.utils` are **context managers** that yield a `Path` to a temporary PDF; the file (and Chrome's scratch files) are cleaned up on exit, so read the bytes inside the `with` block:

```python
from baseapp_pdf.utils import render_to_pdf, render_template_to_pdf

# A local HTML file path or a URL string.
with render_to_pdf(source="path/to/file.html") as pdf_file:      # or source="https://example.com"
    pdf_bytes = pdf_file.read_bytes()

# A Django template name (or a Template object) + context.
context = {"pdf_title": "My PDF", "pdf_margins": "1cm 1cm"}       # plus your template variables
with render_template_to_pdf(source="pdfs/my-template.html", context=context) as pdf_file:
    pdf_bytes = pdf_file.read_bytes()
```

Output is validated before being yielded: an empty file, or one whose text contains Chrome render errors (`ERR_FILE_NOT_FOUND` for a missing local file, `DNS_PROBE_FINISHED_NXDOMAIN` for an unresolvable URL), raises `BaseAppBackendPDFRenderToPDFException`. All exceptions derive from `BaseAppBackendPDFException` (`baseapp_pdf.exceptions`).

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

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).
