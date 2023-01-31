from django.contrib.auth.models import User as DjUser
from django.db import models

from drf_view_action_permissions.mixin import PermissionModelMixin


class User(DjUser, PermissionModelMixin):
    class Meta(DjUser.Meta):
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
