from django.db.models import IntegerChoices
from django.utils.translation import gettext_lazy as _


class CommentStatus(IntegerChoices):
    DELETED = 0, _("deleted")
    PUBLISHED = 1, _("published")
