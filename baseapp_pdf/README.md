# BaseApp PDF Generation

Reusable Django app for PDF generation and rendering. This package leverages google-chrome to print to pdf.
This means you can render any webpage or any local rendered html files with full css support.

## Features

- Render URLs to PDF
- Render local HTML files to PDF
- Render Django templates to PDF
- Command-line utilities for PDF generation
- Support for custom templates and styling
- Example template with invoice-like formatting

## How to install:

Install in your environment:

```bash
pip install baseapp-backend[pdf]
```

And run provision or manually `pip install -r requirements/base.ext`

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_pdf` to your project's `INSTALLED_APPS`

### Basic Usage

You can use the provided management commands to generate PDFs:

1. Convert an HTML file to PDF:
```bash
python manage.py render_to_pdf --source path/to/your/file.html --destination /path/to/output/dir
# OR
python manage.py render_to_pdf --source http://your_url.com --destination /path/to/output/dir
```

2. Generate a PDF from the example template:
```bash
python manage.py render_example_template_to_pdf --destination /path/to/output/dir
```

### Using in Your Code

You can use the utility functions directly in your code:

```python
from baseapp_pdf.utils import render_to_pdf, render_template_to_pdf

# Convert HTML file to PDF
with render_to_pdf(source="path/to/file.html") as pdf_file:
    # pdf_file is a Path object pointing to the generated PDF
    pdf_bytes = pdf_file.read_bytes()

# Render a template to PDF
context = {
    "pdf_title": "My PDF",
    "pdf_margins": "1cm 1cm",
    # Add your template context here
}
with render_template_to_pdf(source="template-path", context=context) as pdf_file:
    pdf_bytes = pdf_file.read_bytes()
```

## Example Template

The app includes an example template that demonstrates how to create PDFs with:
- Custom headers and footers
- Tables and formatting
- Dynamic content
- Professional invoice-like layout

You can use this as a starting point for your own templates.

## How to develop

Clone the project inside your project's backend dir:

```bash
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```bash
pip install -e baseapp-backend/baseapp-pdf
```

The `-e` flag will make it so any changes you make in the cloned repo files will affect the project.