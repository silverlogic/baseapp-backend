import django_filters
import swapper
from baseapp_core.graphql import get_pk_from_relay_id
from django.db.models import Q

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")


class ChatRoomFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")
    profile_id = django_filters.CharFilter(method="filter_profile_id")

    order_by = django_filters.OrderingFilter(fields=(("created", "created"),))

    class Meta:
        model = ChatRoom
        fields = ["q", "order_by"]

    def filter_q(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(participants__profile__name__icontains=value)
        )

    def filter_profile_id(self, queryset, name, value):
        pk = get_pk_from_relay_id(value)
        return queryset.filter(participants__profile_id=pk)
