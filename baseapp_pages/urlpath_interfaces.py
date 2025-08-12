from typing import Optional, Type

from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from baseapp_pages.models import URLPath


class URLPathTargetMixin(models.Model):
    """Mixin for models that want to be URLPath targets"""

    url_paths = GenericRelation(
        URLPath,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )

    class Meta:
        abstract = True

    def get_graphql_object_type(self) -> Type:
        raise NotImplementedError

    def get_permission_check(self, user: AbstractUser) -> bool:
        return True

    def create_url_path(self, path: str, language: Optional[str] = None, is_active: bool = True):
        if not self.pk:
            raise ValueError("Save the instance before creating URL paths.")
        return self.url_paths.create(path=path, language=language, is_active=is_active)

    def update_url_path(self, path: str, language: Optional[str] = None, is_active: bool = True):
        if not self.pk:
            raise ValueError("Save the instance before updating URL paths.")
        primary_path = self.url_path
        if primary_path:
            primary_path.path = path
            primary_path.language = language
            primary_path.is_active = is_active
            primary_path.save()
        else:
            self.create_url_path(path, language, is_active)

    def deactivate_url_paths(self):
        if self.pk:
            self.url_paths.update(is_active=False)

    def delete_url_paths(self):
        if self.pk:
            self.url_paths.all().delete()
