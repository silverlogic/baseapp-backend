import django_filters
from django.contrib.auth import get_user_model
from django.db.models import Q


class UsersFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_by_q")

    order_by = django_filters.OrderingFilter(
        fields=(
            ("date_joined", "date_joined"),
            ("last_login", "last_login"),
        )
    )

    class Meta:
        model = get_user_model()
        fields = ["q", "order_by"]

    def filter_by_q(self, queryset, name, value):
        return queryset.filter(
            Q(profile__name__icontains=value) |
            Q(profile__name__icontains=value) |
            Q(email__icontains=value)
        )
