import django_filters
import swapper
from django.db.models import Q, QuerySet

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


class ProfileMemberFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    class Meta:
        model = ProfileUserRole
        fields = ["role", "status", "q"]

    def filter_q(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        return queryset.filter(
            Q(user__profile__name__icontains=value) | Q(user__email__icontains=value)
        )


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
