import typing

from django.db import models
from django.db.models import ExpressionWrapper, Q
from django.utils import timezone


class BaseAPIKeyQuerySet(models.QuerySet):
    def add_is_expired(self) -> typing.Self:
        if self.query.annotations.get("is_expired") is not None:
            return self
        return self.annotate(
            is_expired=ExpressionWrapper(
                Q(expiry_date__isnull=False) & Q(expiry_date__lte=timezone.now().date()),
                output_field=models.BooleanField(),
            ),
        )
