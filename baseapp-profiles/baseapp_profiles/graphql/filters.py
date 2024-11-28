import django_filters
import swapper
from django.db.models import Q

Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfileFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")

    order_by = django_filters.OrderingFilter(
        fields=(
            ("created", "created"),
            ("followers_count__total", "followers_count_total"),
            ("following_count__total", "following_count_total"),
        )
    )

    class Meta:
        model = Profile
        fields = ["q", "order_by"]

    def filter_q(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(url_paths__path__icontains=value))
