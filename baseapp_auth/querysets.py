from constance import config
from django.db import models
from django.db.models import ExpressionWrapper, F, Q, Value
from django.db.models.functions import Cast
from django.utils import timezone


class UserQuerySet(models.QuerySet):
    def add_is_password_expired(self):
        if self.query.annotations.get("is_password_expired") is not None:
            return self
        return self.annotate(
            password_expiry_date=ExpressionWrapper(
                F("password_changed_date")
                + Cast(
                    Value(
                        timezone.timedelta(days=max(0, config.USER_PASSWORD_EXPIRATION_INTERVAL))
                    ),
                    output_field=models.DurationField(),
                ),
                output_field=models.DateTimeField(),
            ),
            is_password_expired=ExpressionWrapper(
                Q(password_expiry_date__date__lte=timezone.now().date()),
                output_field=models.BooleanField(),
            ),
        )
