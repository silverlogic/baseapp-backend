# Django Allauth Template Customizations

This directory contains customized templates for django-allauth. All templates have been modified to use Bootstrap 5.3.2 for styling and improved user experience.

## Overview

The templates in this directory override the default django-allauth templates to provide:
- Modern Bootstrap 5.3.2 styling
- Responsive design
- Consistent branding with BaseApp logo
- Improved error handling and validation display
- Better user experience with form-floating labels

## Template Structure

```
allauth/
├── layouts/
│   ├── base.html          # Base layout (heavily customized)
│   └── entrance.html      # Custom layout for auth pages (created from scratch)
├── elements/
│   ├── alert.html         # Alert messages
│   ├── button.html        # Button elements
│   ├── field.html         # Form field elements
│   ├── form.html          # Form wrapper
│   ├── form__entrance.html # Form for entrance pages
│   ├── h1__entrance.html  # H1 heading for entrance pages
│   └── panel.html         # Panel/card component
└── account/
    ├── login.html         # Login page
    ├── logout.html        # Logout page
    ├── password_change.html
    └── password_change_done.html
```

## Customizations by Template

### `layouts/base.html`

**Original**: [django-allauth base.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/allauth/layouts/base.html)

**Major Changes**:
1. **Bootstrap 5.3.2 Integration**
   - Added Bootstrap CSS/JS via CDN
   - Added custom navbar styles (background: `rgb(249, 250, 251)`, 24px left padding)

2. **HTML Structure**
   - Added `{% load static %}` and `{% get_current_language %}`
   - Added `lang="{{ LANGUAGE_CODE }}"` and `data-bs-theme="auto"` to `<html>`
   - Added meta tags: `charset`, `description` (with block), `generator`
   - Added Bootstrap utility classes to `<body>`: `min-vh-100 d-flex flex-shrink-0 flex-column`

3. **Navigation**
   - **Removed**: Original simple menu with list of links
   - **Added**: Bootstrap responsive navbar with:
     - BaseApp logo (`logo-full-colored.svg`) linking to `admin:index`
     - Authentication buttons (Sign In/Sign Out) in the top right
     - Mobile-responsive navbar toggler

4. **Content Structure**
   - **Removed**: Messages display (moved to `entrance.html`)
   - **Removed**: Original menu structure
   - **Simplified**: `body` block now only contains `content` block

5. **Documentation**
   - Added comprehensive comment block documenting all modifications
   - Included instructions for future updates

### `layouts/entrance.html`

**Original**: This template does not exist in django-allauth. It was created from scratch.

**Purpose**: Provides a centered layout for authentication pages (login, signup, password reset, etc.)

**Features**:
- Bootstrap grid system for responsive centering
- Full-height background with `bg-body-secondary`
- Centered card with shadow and rounded corners (`bg-white shadow rounded-4`)
- Messages display using `{% element alert %}` with slots
- Padding (`p-5`) for content area

**Bootstrap Classes Used**:
- `flex-grow-1 bg-body-secondary d-flex flex-column justify-content-center`
- `container`, `row`, `col col-lg-4`
- `bg-white shadow rounded-4`, `p-5`

### `elements/field.html`

**Original**: [django-allauth field.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/allauth/elements/field.html)

**Major Changes**:

1. **Bootstrap Form Classes**
   - Checkbox/Radio: `form-check`, `form-check-input`, `form-check-label`
   - Text inputs: `form-control`, `form-floating`
   - Help text: `form-text`
   - Spacing: `mb-3` on all field containers

2. **Error Handling**
   - Added `is-invalid` class when `attrs.errors` is present
   - Added `d-block` to `invalid-feedback` divs for visibility (especially important for checkbox/radio/textarea)
   - Error messages now properly visible for all input types

3. **Form Floating Labels**
   - Support for `form-floating` when `attrs.unlabeled` is true
   - Placeholder used as floating label text

4. **Input Styling**
   - Added `rounded-3` class to text inputs
   - Added `checked` attribute support for checkbox/radio inputs
   - Removed empty `class=""` attributes from labels

5. **Textarea Support**
   - Proper error styling with `is-invalid`
   - Error messages with `d-block` for visibility

### `elements/button.html`

**Original**: [django-allauth button.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/allauth/elements/button.html)

**Major Changes**:

1. **Bootstrap Button Classes**
   - Base: `btn`
   - Variants: `btn-primary`, `btn-secondary`, `btn-danger`, `btn-warning`
   - Outlines: `btn-outline-*`
   - Sizes: `btn-lg`, `btn-sm`
   - Link style: `btn-link`

2. **Icon Support**
   - Added inline SVG icons for action buttons:
     - Trash icon for `delete` tag
     - Edit icon for `edit` tag
   - Icons are hidden when `tool` tag is present (icon-only buttons)

3. **Tag Support**
   - `prominent` → `btn-lg`
   - `minor` → `btn-sm`
   - `danger` → `btn-danger`
   - `secondary` → `btn-secondary`
   - `warning` → `btn-warning`
   - `link` → `btn-link`
   - `outline` → `btn-outline-*`

4. **Code Quality**
   - Fixed Pythonic syntax: `"tool" not in attrs.tags` (was `not "tool" in attrs.tags`)

### `elements/form.html`

**Original**: [django-allauth form.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/allauth/elements/form.html)

**Major Changes**:

1. **Bootstrap Card Structure**
   - Forms wrapped in `card` class (when visible fields exist)
   - `card-body` for form fields
   - `card-footer` for form actions (buttons)

2. **Error Display**
   - Non-field errors displayed using Bootstrap alerts: `alert alert-danger`

3. **Conditional Styling**
   - `no_visible_fields` attribute removes card styling for hidden forms

### `elements/alert.html`

**Original**: [django-allauth alert.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/allauth/elements/alert.html)

**Major Changes**:

1. **Bootstrap Alert Classes**
   - Base: `alert alert-xs` (custom size)
   - Level mapping:
     - `error` → `alert-danger`
     - `success` → `alert-success`
     - `warning` → `alert-warning`
     - Default → `alert-info`

### `elements/h1__entrance.html`

**Original**: [django-allauth h1.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/allauth/elements/h1.html)

**Major Changes**:

1. **Bootstrap Typography**
   - `fw-bold` for bold font weight
   - `fs-2` for font size

### `elements/panel.html`

**Original**: [django-allauth panel.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/allauth/elements/panel.html)

**Major Changes**:

1. **Bootstrap Card Structure**
   - Wrapped in `card` class with `mb-4` margin
   - `card-body` for main content
   - `card-title` for panel title (h5)
   - `card-footer` for actions (conditional)

### `elements/form__entrance.html`

**Original**: [django-allauth form.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/allauth/elements/form.html)

**Major Changes**:

1. **Removed Card Styling**
   - Extends `form.html` but removes `card` class via empty `form_class` block
   - Used for entrance pages where card styling is handled by `entrance.html` layout

### `account/login.html`

**Original**: [django-allauth login.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/account/login.html)

**Major Changes**:

1. **Action URL**
   - Added `{% url 'account_login' as action_url %}` before form element
   - Ensures `action_url` is properly defined

2. **Form Structure**
   - Uses `unlabeled=True` for form fields (enables form-floating)
   - Uses `prominent` tag for submit button

### `account/password_change.html`

**Similar to `login.html`**:
- Uses `unlabeled=True` for form fields
- Uses `prominent` tag for submit button
- Proper action URL definition

### `account/logout.html`

**Original**: [django-allauth logout.html](https://github.com/pennersr/django-allauth/blob/main/allauth/templates/account/logout.html)

**Major Changes**:

1. **Layout**
   - Extends `entrance.html` for consistent styling
   - Uses Bootstrap card structure via `{% element panel %}`

2. **Structure**
   - Uses `{% element h1 %}` for page title
   - Confirmation message in panel body
   - Form with submit button in panel actions slot

3. **Form**
   - Action URL properly defined: `{% url 'account_logout' as action_url %}`
   - Uses `tags="inline"` for form styling
   - Submit button with `tags="primary,prominent"` for emphasis

### `account/password_change_done.html`

**Custom Template**:
- Uses `{% element panel %}` with `body` and `actions` slots
- Success alert using `{% element alert level="success" %}`
- "Go to Admin" button linking to `admin:index`

## Bootstrap Version

All templates use **Bootstrap 5.3.2** loaded via CDN:
- CSS: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css`
- JS: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js`

## Updating Templates

When django-allauth releases updates:

1. **Compare with originals**: Use the GitHub links provided in each template section
2. **Preserve customizations**: Maintain Bootstrap classes and custom structure
3. **Test thoroughly**: Ensure all authentication flows work correctly
4. **Check for new blocks**: Look for new template blocks that may need customization

## Key Design Decisions

1. **Bootstrap Integration**: Chose Bootstrap 5.3.2 for consistency with modern web standards
2. **Form Floating Labels**: Enabled for better UX on entrance pages
3. **Card-based Layout**: Used Bootstrap cards for visual hierarchy
4. **Responsive Design**: All layouts are mobile-friendly
5. **Error Visibility**: Ensured error messages are always visible with `d-block` class
6. **Branding**: Integrated BaseApp logo in navbar

## Files Not Customized

The following django-allauth templates are **not** overridden and use defaults:
- `account/signup.html` (if exists)
- Email templates (in `account/email/`)
- Social account templates
- MFA templates (if used)

## References

- [Django Allauth Documentation](https://docs.allauth.org/)
- [Django Allauth GitHub](https://github.com/pennersr/django-allauth)
- [Bootstrap 5.3.2 Documentation](https://getbootstrap.com/docs/5.3/)

