import django_filters
import swapper
from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


class ProfileMemberFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    class Meta:
        model = ProfileUserRole
        fields = ["role", "status", "q"]

    def filter_q(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        User = get_user_model()
        match = Q(**{f"user__{User.get_email_field_name()}__icontains": value})
        if any(field.name == "profile" for field in User._meta.get_fields()):
            # Users have a profile of their own in most projects, but not all.
            match |= Q(user__profile__name__icontains=value)
        return queryset.filter(match)


class ProfileInvitationFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    class Meta:
        model = ProfileUserRole
        fields = ["role", "status", "q"]

    def filter_q(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        return queryset.filter(
            Q(invited_email__icontains=value)
            | Q(invited_first_name__icontains=value)
            | Q(invited_last_name__icontains=value)
        )
