import django_filters
import swapper

Notification = swapper.load_model("notifications", "Notification")


class NotificationFilter(django_filters.FilterSet):
    verbs = django_filters.CharFilter(method="filter_by_verbs")

    class Meta:
        model = Notification
        fields = ["level", "unread"]

    def filter_by_verbs(self, queryset, name, value):
        verbs = value.split(",")
        return queryset.filter(verb__in=verbs)
