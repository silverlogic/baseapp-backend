from django.contrib.auth.models import AbstractUser
from django.db import models

from baseapp_core.graphql.models import RelayModel
from baseapp_drf_view_action_permissions.mixin import PermissionModelMixin


class DRFUser(AbstractUser, PermissionModelMixin, RelayModel):
    pass


class TestModel(models.Model):
    title = models.CharField(max_length=50, blank=True)

    class Meta:
        permissions = [
            ("view_testmodel_list", "Can List all testmodel"),
            ("test_disable", "Can disable test"),
            ("list_tests", "Can list tests"),
            ("custom_action_testmodel", "Can custom action testmodel"),
            ("custom_detail_action_testmodel", "Can custom detail action testmodel"),
        ]
