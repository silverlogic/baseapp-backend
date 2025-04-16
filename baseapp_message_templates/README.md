
# BaseApp Message Templates - Django

This app provides the integration of custom e-mail and sms template configuration with The SilverLogic's [BaseApp](https://bitbucket.org/silverlogic/baseapp-django-v2).

## How to install:

Install the package with `pip install baseapp-backend[messagetemplates]`.

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

## EmailTemplate model

This model is responsible for customizing your e-mail template and sending mail. At minimum, an instance of `EmailTemplate` must have a unique name and either a SendGrid template ID or some custom HTML content. The `subject`, `plain_text_content`, and `attachments` are optional.

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

When adding HTML content to a template through the Django Admin, the "source" option must be selected in the text field.

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
