import django_filters
import swapper
from django.db.models import Case, IntegerField, Q, Value, When

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


class ProfileFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    order_by = django_filters.OrderingFilter(
        fields=(
            ("created", "created"),
            ("name", "name"),
            ("followers_count__total", "followers_count_total"),
            ("following_count__total", "following_count_total"),
        )
    )

    class Meta:
        model = Profile
        fields = ["q", "order_by"]

    def filter_q(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(url_paths__path__icontains=value))


class MemberOrderingFilter(django_filters.OrderingFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra["choices"] += [
            ("status", "Status"),
        ]

    def filter(self, qs, value):
        if value is None:
            return qs

        if any(v == "status" for v in value):
            status_order = Case(
                When(status=ProfileUserRole.ProfileRoleStatus.PENDING.value, then=Value(1)),
                When(status=ProfileUserRole.ProfileRoleStatus.INACTIVE.value, then=Value(2)),
                When(status=ProfileUserRole.ProfileRoleStatus.ACTIVE.value, then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            )
            return qs.order_by(status_order)

        return super().filter(qs, value)


class MemberFilter(django_filters.FilterSet):
    order_by = MemberOrderingFilter()
    q = django_filters.CharFilter(method="filter_q")

    def filter_q(self, queryset, name, value):
        return queryset.filter(
            Q(user__profile__name__icontains=value) | Q(user__email__icontains=value)
        )

    class Meta:
        model = ProfileUserRole
        fields = ["role", "order_by", "q"]
