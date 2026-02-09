import pytest
from django.contrib.auth.models import Permission

from baseapp_auth.fields import GroupedPermissionField
from baseapp_auth.widgets import GroupedPermissionWidget


@pytest.mark.django_db
def test_grouped_permission_field_initialization():
    field = GroupedPermissionField()

    assert isinstance(field, GroupedPermissionField)
    assert isinstance(field.widget, GroupedPermissionWidget)


@pytest.mark.django_db
def test_grouped_permission_field_queryset():
    field = GroupedPermissionField()

    assert field.queryset.model is Permission
    assert field.queryset.exists()


@pytest.mark.django_db
def test_grouped_permission_field_queryset_has_content_type_loaded():
    field = GroupedPermissionField()
    permission = field.queryset.first()

    assert permission.content_type is not None


@pytest.mark.django_db
def test_widget_choices_are_bound_from_field_queryset():
    field = GroupedPermissionField()
    widget = field.widget

    choices = list(widget.choices)

    assert choices, "Widget choices should not be empty"
    value, label = choices[0]

    assert value is not None
    assert isinstance(label, str)
