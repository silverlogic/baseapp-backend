from django.db.models import Manager
from django.db.models.query import QuerySet

from .status import CommentStatus


class SoftDeleteQuerySet(QuerySet):
    """
    A custom QuerySet class for soft deletion of objects.

    Methods:
    - delete(): Soft deletes all objects in the QuerySet.
    - hard_delete(): Hard deletes all objects in the QuerySet.

    """

    def delete(self):
        self.update(status=CommentStatus.DELETED)

    def hard_delete(self):
        return super().delete()


class NonDeletedComments(Manager):
    """Automatically filters out soft deleted objects from QuerySets"""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).exclude(status=CommentStatus.DELETED)
