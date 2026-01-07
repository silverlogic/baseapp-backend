# fields.py
from django.contrib.auth.models import Permission
from django.forms import ModelMultipleChoiceField

from .widgets import GroupedPermissionWidget


class GroupedPermissionField(ModelMultipleChoiceField):
    widget = GroupedPermissionWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("queryset", Permission.objects.select_related("content_type").all())
        super().__init__(*args, **kwargs)
