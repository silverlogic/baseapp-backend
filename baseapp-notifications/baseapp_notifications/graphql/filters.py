import django_filters
import swapper

Notification = swapper.load_model("notifications", "Notification")


class NotificationFilter(django_filters.FilterSet):
    class Meta:
        model = Notification
        fields = ["level", "unread"]
