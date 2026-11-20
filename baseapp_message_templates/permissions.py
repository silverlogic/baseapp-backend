from django.contrib.auth.backends import BaseBackend

from .models import EmailTemplate

# Model-level permissions that also answer object-level checks on an EmailTemplate.
EMAIL_TEMPLATE_PERMISSIONS = frozenset(
    {
        "baseapp_message_templates.view_emailtemplate",
        "baseapp_message_templates.change_emailtemplate",
        "baseapp_message_templates.send_test_emailtemplate",
    }
)


class MessageTemplatesPermissionsBackend(BaseBackend):
    """Answers ``user.has_perm(perm, email_template)`` with the model-level permission.

    Django's ``ModelBackend`` grants nothing when an object is passed, so without this backend
    an object-level check fails even for staff who hold the permission. Projects grant the
    permissions as usual (groups, user permissions) or add their own backend after this one.
    """

    def has_perm(self, user_obj, perm, obj=None) -> bool:
        if perm not in EMAIL_TEMPLATE_PERMISSIONS or not isinstance(obj, EmailTemplate):
            return False
        if not user_obj.is_active:
            return False
        return user_obj.has_perm(perm)
