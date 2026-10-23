# BaseApp Message Templates

Reusable app for email and SMS templates: edit content in the Django admin (Prose or CKEditor), render it through Jinja2, and send via SendGrid (template id or dynamic) or plain custom HTML. Projects can also [declare templates in code](#code-declared-templates-registry) with file defaults and let staff override parts of them.

`baseapp_message_templates` follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin so it participates in `INSTALLED_APPS` aggregation. It contributes no auth backends, GraphQL roots, or URLs, and its models (`EmailTemplate`, `Attachment`, `SmsTemplate`) are **concrete** (not swappable) — the package ships their migrations, so there's nothing to subclass.

## How to install

Install the package with `pip install baseapp-backend[messagetemplates]`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

1. Add `baseapp_message_templates` to `INSTALLED_APPS` and run `./manage.py migrate`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_message_templates",
    # ...
]
```

2. Configure the admin editor, Jinja2 `TEMPLATES`, and (optionally) SendGrid — see the sections below.

## Choose the editor (Prose or CKEditor)

By default the admin uses **django-prose-editor**. You can switch to **CKEditor**
by setting a Django setting and adding the app.

```py
# settings.py
MESSAGE_TEMPLATES_EDITOR = "prose"  # or "ckeditor"

# Only required if you choose CKEditor:
INSTALLED_APPS += ["ckeditor"]
```

### Prose editor requirements (admin)

`django-prose-editor` uses importmaps for its JavaScript. Since
`django-js-asset` 4.0 the widget carries its own `ImportMap` in its `Media`,
which `js_asset.Media` merges and renders automatically. No context processor
and no template override are required.

Do not add `js_asset.context_processors.importmap` to `context_processors`:
that module was removed in `django-js-asset` 4.0 and referencing it raises
`ModuleNotFoundError` on every Django-template render, including
`/admin/login/`.

### Sanitization (recommended)

Prose sanitization is generated from your enabled extensions and runs on save.
That means HTML tags/attributes not covered by your extensions can be stripped.
Configure these in settings:

```py
PROSE_EDITOR_EXTENSIONS = {
    "Bold": True,
    "Italic": True,
    "BulletList": True,
    "ListItem": True,
    "Link": {"protocols": ["http", "https", "mailto"]},
    # ...
}
PROSE_EDITOR_SANITIZE = True
```

Docs:
- https://django-prose-editor.readthedocs.io/en/latest/configuration.html
- https://django-prose-editor.readthedocs.io/en/stable/sanitization.html

### Images (Prose ImageDialog)

CKEditor includes a built-in image dialog. Prose does **not** ship an image
dialog by default, so this package includes a small custom image extension
(`ImageDialog`) that adds an image button to the toolbar.

**How to use it**

1. Ensure Prose is the selected editor:
   ```py
   MESSAGE_TEMPLATES_EDITOR = "prose"
   ```
2. Make sure the extension is enabled:
   ```py
   PROSE_EDITOR_EXTENSIONS = {
       # ...
       "ImageDialog": True,
   }
   ```
3. Make sure the custom extension JS is registered:
   ```py
   DJANGO_PROSE_EDITOR_EXTENSIONS = [
       {
           "js": ["baseapp_message_templates/prose/image_dialog.js"],
           "extensions": {
                "ImageDialog": html_tags(
                    tags=["img"],
                    attributes={
                        "img": [
                            "src",
                            "alt",
                            "title",
                            # ...
                        ]
                    }
                )
            },
       },
   ]
   ```

**Sanitization**

The `ImageDialog` extension also adds a sanitization allowlist for common
`<img>` attributes. If you need extra attributes, update the allowlist in
`DJANGO_PROSE_EDITOR_EXTENSIONS`.

- https://django-prose-editor.readthedocs.io/en/latest/configuration.html
- https://django-prose-editor.readthedocs.io/en/latest/custom_extensions.html


## Configure template settings

```py
TEMPLATES  =  [
	{
		"BACKEND": "django_jinja.backend.Jinja2",
		"DIRS": [str(APPS_DIR  /  "templates")], # change this to wherever your base templates are stored
		"APP_DIRS": True,
        "NAME": "jinja2",
		"OPTIONS": {
			"match_extension": ".j2",
			"constants": {"URL": URL, "FRONT_URL": FRONT_URL},
		},
	},
	{
		"BACKEND": "django.template.backends.django.DjangoTemplates",
		"DIRS": [
			str(APPS_DIR  /  "templates"), # change this to wherever your base templates are stored
		],
		"APP_DIRS": True,
		"OPTIONS": {
			"context_processors": [
				"django.template.context_processors.debug",
				"django.template.context_processors.request",
				"django.contrib.auth.context_processors.auth",
				"django.contrib.messages.context_processors.messages",
			],
			"libraries": {
				"filter": "baseapp_message_templates.filters",
			},
		},
	},
]
```

## Default Email Template

In our Django application, you have the option to use a default email template. This template acts as a wrapper for your other email templates, ensuring a consistent layout and style across all your emails.


### Using the Default Template

To effectively utilize the default template:

1. **Create the Default Template**

   Ensure your default template includes a placeholder for the child template content. This is done using the `template_content|safe` variable in your Jinja2 template. 

   Example:
   ```html
   <html>
   <body>
     <div>
       <!-- Your default template layout -->
       <div class="content">
         {{ template_content|safe }}
       </div>
       <!-- More of your default template layout -->
     </div>
   </body>
   </html>


2. **Render Child Templates**

	When rendering a child template, pass the content as a string to template_content. `Jinja2` will insert this content into the default template at the location of {{ template_content|safe }}.

3. **Sanitize for Security:**
	To ensure security, especially since we're using the safe filter, it's important to sanitize `template_content` to prevent XSS (Cross-Site Scripting) attacks. This process removes or neutralizes any potentially harmful scripts that might be part of the content.


### Setting Default Base Template (Optional)

If you want to use a default base template that your emails will automatically inherit from, add the path to that template in your Django settings. This configuration allows you to define a consistent layout or design for your emails. Note that this base template won't apply to emails created directly in SendGrid.

In your `settings.py`:

```python
DEFAULT_EMAIL_TEMPLATE = "path/to/your/default/template" # ex: "emails/base-template"
```

## Setup SendGrid credentials (optional)

If you want to use SendGrid to send mail, add these settings to your `settings/base.py`:

```py
DJMAIL_REAL_BACKEND = "sendgrid_backend.SendgridBackend"

SENDGRID_API_KEY = env("SENDGRID_API_KEY")

SENDGRID_SANDBOX_MODE_IN_DEBUG = False
```

## Code-declared templates (registry)

Projects that keep their email copy in template files can declare each email in code and let
staff override parts of it, without a database row being required to send. Register templates
from `AppConfig.ready()`:

```python
from django.utils.translation import gettext_lazy as _

from baseapp_message_templates.registry import Placeholder, register_email_template


class OrdersConfig(AppConfig):
    def ready(self) -> None:
        register_email_template(
            "orders/shipped",
            label=_("Order shipped"),
            group="orders",
            description=_("Sent when an order leaves the warehouse"),
            placeholders=[
                Placeholder("order.number", help=_("Order number"), sample="A-1001"),
                Placeholder("user.first_name", help=_("First name"), sample="Ada"),
            ],
            editable=("subject",),  # any of "subject", "plain_text_content", "html_content"
            sample_context=lambda: {"order": {"items": [{"name": "Mug"}]}},  # optional
        )
```

The default copy lives in three files, found by `BASEAPP_MESSAGE_TEMPLATES_FILE_PATTERNS`
(`emails/orders/shipped.subject.txt.j2`, `.body.txt.j2` and `.body.html.j2` by default). The
html file is optional. Pass `subject_template=`, `text_template=` or `html_template=` to point a
template at other files. Any configured engine may render the files (Jinja2 or Django).

Render and send with your own email code:

```python
from baseapp_message_templates.registry import render_email_template

rendered = render_email_template(
    "orders/shipped",
    {"order": order, "user": user},
    recipient=user.email,              # passed to BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT
    overrides={"subject": "..."},      # optional per-send text for editable parts
    fallback="orders/default",         # optional: used when the files of the name are missing
)
rendered.subject, rendered.body_text, rendered.body_html, rendered.customized
```

How each part is resolved:

- For an **editable** part, the first non-blank of `overrides[part]` and the field of the
  `EmailTemplate` row with the same name wins. It is rendered with the **Django** template engine
  against a context limited to the declared placeholder roots (`order`, `user` above) plus
  `BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT`, so staff text cannot reach other context values.
  Autoescaping is off for the subject and the plain text and on for the html.
- Otherwise the part's **file** is rendered with the full context through `render_to_string`.
- The html part also receives `body_text`, the rendered plain text, so a plain-text override
  flows into a branded html layout (`{{ body_text|e|linebreaks }}` or similar).
- The subject's whitespace is collapsed to single spaces. A missing html file renders as `""`.
- Names that are **not registered** render their files by pattern and ignore overrides, so
  `render_email_template` can replace a project's own `render_to_string` calls gradually.

`EmailTemplate.send()` and `send_template_email()` use the registry for registered names (the
files own their layout, so `use_base_template` does not apply); `send_template_email()` also
sends a registered name that has no row yet. Unregistered names behave exactly as before.

Other helpers in `baseapp_message_templates.registry`:

| Function | Purpose |
|---|---|
| `preview_email_template(name, overrides=None, *, recipient=None)` | Renders with sample values: placeholder `sample`s expanded into nested dicts, merged with `sample_context()`. Values without a sample print as `{{ name }}`. The result is a `RenderedEmail` with a `preview_subject` alias. |
| `validate_override(name, field, text) -> list[str]` | Error messages for staff text: Django template syntax, tags outside `ALLOWED_OVERRIDE_TAGS` (`include`, `load`, `debug`… are rejected) and placeholder roots that were not declared. Blank text is valid (it resets the part). |
| `sync_email_templates()` | Creates a blank `EmailTemplate` row per registered name. Runs after every `migrate` and as `./manage.py sync_email_templates`. Existing rows are never changed. |
| `get_default_source(name, part)` | Raw source of a part's default file, for showing the default next to an override. |
| `is_customized(row)` | Whether a row overrides an editable part. |
| `email_templates` | The registry itself (`get`, `list(group=None)`, `is_registered`, `unregister`). |

### Settings

| Setting | Default | Purpose |
|---|---|---|
| `BASEAPP_MESSAGE_TEMPLATES_FILE_PATTERNS` | `{"subject": "emails/{name}.subject.txt.j2", "text": "emails/{name}.body.txt.j2", "html": "emails/{name}.body.html.j2"}` | Where the default copy of a name lives. Partial dicts are merged over the default. |
| `BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT` | `None` | Dotted path to `callable(recipient) -> dict` with values every email receives (site name, support address…). Its keys may be used in overrides without being declared. |
| `BASEAPP_MESSAGE_TEMPLATES_TEST_SENDER` | `None` | Dotted path to `callable(email_message, *, template, user) -> None` that delivers test emails (`template` is the name), e.g. through the project's logged email backend. `None` calls `email_message.send()`. |
| `BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT` | `"10/h"` | Test emails per user per period (`s`, `m`, `h`, `d`), counted in the default cache. `None` disables the limit. |

## EmailTemplate model

This model is responsible for customizing your e-mail template and sending mail. At minimum, an instance of `EmailTemplate` must have a unique name and either a SendGrid template ID or some custom HTML content. The `subject`, `plain_text_content`, and `attachments` are optional.

`plain_text_content` is a plain `TextField`: it is never sanitized as HTML, so `&` and `<` are
stored as typed. For a [registered](#code-declared-templates-registry) name, the row only holds
staff overrides; its blank fields fall back to the template files.

### Static attachments

`Attachment` instances that are linked to an `EmailTemplate` represent static files that will be attached to every message sent via that template, regardless of recipient or context. These attachments will be sent regardless of whether the e-mail is sent through a SendGrid template or a custom HTML template.

## Sending mail via SendGrid template

If a `sendgrid_template_id` is provided on an instance of `EmailTemplate`, a SendGrid template can be used to send mail. In order to send mail via SendGrid template, you can use the `send_sendgrid_email` util, or manually do so by creating at least one `Personalization`. Each `Personalization`will contain the email of a recipient and any context that must be provided to the template. A `Personalization` can be created like so:

```py
# This step is only necessary if not using the `send_sendgrid_email` util
from baseapp_message_templates.sendgrid import get_personalization

personalization = get_personalization("john@test.com", {"message": "Hello there."})
```

### Sending sendgrid emails

The `send_sendgrid_email` in `email_utils` automatically handles the fetching of the email template and the creation of the personalizations. The function takes two arguments: `template_name`, which is the name of the `EmailTemplate` to be used, and `content`, which is a list of tuples containing a recipient email and message pair.

```py
from baseapp_message_templates.email_utils import send_sendgrid_email
 # Template name: "Test Template"
 # Recipient: "john@test.com"
 # Message: "Hello there."

send_sendgrid_email("Test Template", [("john@test.com", "Hello there.")])
```

This util automatically handles sending multiple messages to multiple recipients. You just need to provide the recipient/message tuple in the content list.

```py
from baseapp_message_templates.email_utils import send_sendgrid_email

send_sendgrid_email("Test Template", [("john@test.com", "Hello there."), ("jane@test.com", "Hi!")])
```
If needed, it is possible to manully send emails using the `send_via_sendgrid` or `mass_send_via_sendgrid` methods.


### Manually sending mail to one recipient

The `send_via_sendgrid` method of `EmailTemplate` can be used to send a single email to one recipient. The method takes one `Personalization` as an argument, as well as an optional list of `attachments` that can be sent along with this particular message.

```py
from baseapp_message_templates.models import EmailTemplate
from baseapp_message_templates.sendgrid import get_personalization

template = EmailTemplate.objects.get("Test Template")

personalization = get_personalization("john@test.com", {"message": "Hello there."})

template.send_via_sendgrid(personalization)
```

### Manually sending mail to multiple recipients

The `mass_send_via_sendgrid` method of `EmailTemplate` can be used to send multiple instances of a template to multiple recipients. The method takes a list of `Personalization` objects as an argument, and each `Personalization` will send a separate message to each recipient with its own context.

```py
from baseapp_message_templates.models import EmailTemplate
from baseapp_message_templates.sendgrid import get_personalization


template = EmailTemplate.objects.get("Test Template")

personalization_1 = get_personalization("john@test.com", {"message": "Hello there."})
personalization_2 = get_personalization("jane@test.com", {"message": "Good morning."})
personalization_list = [personalization_1, personalization_2]

template.mass_send_via_sendgrid(personalization_list)
```

## Sending Mail via custom HTML

If you aren't using SendGrid and instead wish to provide your custom HTML content directly to the `EmailTemplate` instance, this can be done through the `html_content` field. Once `html_content` has been provided, the `send` method of the `EmailTemplate` can be used to send mail. 

### Adding HTML content via Django Admin

When adding HTML content to a template through the Django Admin, the "source"
option must be selected in the text field (CKEditor only). With Prose, the
`HTML` extension enables editing raw HTML.

![enter image description here](https://i.ibb.co/3yCBRy3/Screen-Shot-2023-06-12-at-12-48-17-PM.png)

After saving, the content of the text field will no longer contain the raw HTML that was added. This is a small caveat of the Django Admin. The "raw HTML" field that is displayed underneath the input will display the actual raw HTML content that is currently added to the instance. 

![enter image description here](https://i.ibb.co/0jgms7c/Screen-Shot-2023-06-12-at-12-48-32-PM.png)

### Sending

Once you've added `html_content` to your template, either programatically or through the Django Admin, a message can now be sent through the `send_template_email` util in `email_utils`. This util is a simple wrapper for fetching the email template and sending it using the template's `send` method.

Regardless of the method used, there are two required parameters: `template_name`, which is the name of the `EmailTemplate` to be used, and `recipients`, which is a list of one or more strings containing the e-mail addresses of the recipients. A `context` dict can be passed in optionally if the HTML content is expected one or more key/value pairs to be provided.

The other (optional) params are: `use_base_template`, `extended_with`, `attachments` and `custom_subject`.

The `use_base_template` param will determine whether the message should extend from a base HTML template. If set to `True`, the message will extend from a base template that can be either the base template set in the `DEFAULT_EMAIL_TEMPLATE` setting, or a path to a custom template - which must be provided to the `extended_with` param. Keep in mind that the `send_template_email` util will default `use_base_template` to `True`. 

The `attachments` parameter is a list of one or more files that will be send along with this particular message. These attachments will be sent along with any static attachments that have been attached to the template itself through `Attachment`.

Finally, the `custom_subject` parameter is a string, which will override the copy template subject if passed.

```py
from baseapp_message_templates.email_utils import send_template_email

# The name of the template to be used in this example is `Test Template`
recipients = ["john@test.com"]
context = {"content": "Hello."}
extended_with = "apps/base/templates/test-template.html"

send_template_email("Test Template", recipients, context, True, extended_with)

# Example with attachments and custom subject
attachments = [attch_1, ...]
subject = f'Custom subject {var}'
send_template_email("Test Template", recipients, context, True, extended_with, 
              attachments=attachments, subject=subject)


# If needed, you can also manually send emails by fetching the necessary template:
from baseapp_message_templates.models import EmailTemplate


template = EmailTemplate.objects.get("Test Template")

recipients = ["john@test.com"]
context = {"content": "Hello."}
extended_with = "apps/base/templates/test-template.html"

template.send(recipients, context, True, extended_with)
```


### SmsTemplate Model

The `SmsTemplate` model has two fields:
* `name`: this name must be unique.
* `message`: this is a textfield and does not accept HTML

### Creating migrations for your template

Once you have installed the package you can simply create a migration to input your templates like so:
```py
from __future__ import unicode_literals

from django.db import migrations


def create_object(sms_template, name, message):
    sms_template.objects.create(
        name=name,
        message=message,
    )


def create_sms_templates(apps, schema_migration):
    sms_template = apps.get_model("baseapp_message_templates", "SmsTemplate")

    create_object(
        sms_template,
        "First Template",
        """
            Hello, {{ some_variable }}.
        """,
    )

    create_object(
        sms_template,
        "Second template",
        """
            Hello, {{ some_other_variable }}.
        """,
    )


class Migration(migrations.Migration):
    dependencies = [("some_app", "0002_some_previus_migration")]

    operations = [migrations.RunPython(create_sms_templates, migrations.RunPython.noop)]

```

OBS: make sure that the variables are the right ones that you will pass as context when getting the message.

### Get the template message
To get the template message you can simply use the util functions `get_sms_message` from `sms_utils` passing as first parameter the name of the template and the second parameter the context with your variables if needed.

```py
from baseapp_message_templates.sms_utils import get_sms_message

context = {"some_variable": "some_value"}

message = get_sms_message("First Template", context)
```

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).
