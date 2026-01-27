import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from baseapp_auth.fields import GroupedPermissionField
from baseapp_auth.utils.app_and_model_verbose_names import (
    get_app_and_model_verbose_names,
)


@pytest.mark.django_db
def test_get_app_and_model_verbose_names_returns_verbose_names():
    ct = ContentType.objects.get_for_model(Group)

    app_verbose, model_verbose = get_app_and_model_verbose_names(ct)

    assert app_verbose == "Authentication and Authorization"
    assert model_verbose == "group"


@pytest.mark.django_db
def test_get_app_and_model_verbose_names_fallback_for_missing_model():
    ct = ContentType.objects.get_for_model(Group)

    # Simulate missing model lookup
    ct.model = "nonexistent"

    app_verbose, model_verbose = get_app_and_model_verbose_names(ct)

    assert app_verbose == "Authentication and Authorization"
    assert model_verbose == "nonexistent"


@pytest.mark.django_db
def test_widget_groups_permissions_by_app_and_model(permission_factory):
    permission_factory(Group, "custom_perm_1", "Can do thing A")
    permission_factory(Group, "custom_perm_2", "Can do thing B")

    field = GroupedPermissionField()
    widget = field.widget

    context = widget.get_context("permissions", [], {})

    grouped = context["grouped_permissions"]

    assert "Authentication and Authorization" in grouped
    assert "group" in grouped["Authentication and Authorization"]

    perms = grouped["Authentication and Authorization"]["group"]
    labels = {p["label"] for p in perms}

    assert "Can do thing A" in labels
    assert "Can do thing B" in labels


@pytest.mark.django_db
@override_settings(PERMISSIONS_HIDE_APPS={"auth"})
def test_widget_hides_apps(permission_factory):
    perm = permission_factory(
        Group,
        "hidden_perm",
        "Hidden permission",
    )

    field = GroupedPermissionField()
    widget = field.widget

    widget.choices = field.choices

    context = widget.get_context(
        name="permissions",
        value=[],
        attrs={},
    )

    grouped = context["grouped_permissions"]

    assert "Authentication and Authorization" not in grouped

    all_labels = {
        perm_data["label"]
        for models in grouped.values()
        for perms in models.values()
        for perm_data in perms
    }

    assert perm.name not in all_labels


@pytest.mark.django_db
@override_settings(PERMISSIONS_HIDE_MODELS={"auth.group"})
def test_widget_hides_specific_models(permission_factory):
    permission_factory(Group, "hidden_perm", "Hidden permission")

    field = GroupedPermissionField()
    widget = field.widget

    context = widget.get_context("permissions", [], {})

    grouped = context["grouped_permissions"]

    # App may exist, but model must not
    if "Authentication and Authorization" in grouped:
        assert "group" not in grouped["Authentication and Authorization"]
