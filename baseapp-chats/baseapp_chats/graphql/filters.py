import django_filters
import swapper
from baseapp_core.graphql import get_pk_from_relay_id
from django.db.models import Q

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")


class ChatRoomFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")
    profile_id = django_filters.CharFilter(method="filter_profile_id")
    unread_messages = django_filters.BooleanFilter(method="filter_unread_messages")

    order_by = django_filters.OrderingFilter(fields=(("created", "created"),))

    class Meta:
        model = ChatRoom
        fields = ["q", "order_by"]

    def filter_q(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(participants__profile__name__icontains=value)
        ).distinct()

    def filter_profile_id(self, queryset, name, value):
        pk = get_pk_from_relay_id(value)
        return queryset.filter(participants__profile_id=pk)

    def filter_unread_messages(self, queryset, name, value):
        if value:
            profile_id = self.data.get("profile_id", None)
            try:
                user_profile = self.request.user.profile
            except AttributeError:
                return queryset.none()

            unread_messages_profile_pk = (
                get_pk_from_relay_id(profile_id) if profile_id else user_profile.pk
            )

            return (
                queryset.prefetch_related("unread_messages")
                .filter(
                    unread_messages__profile_id=unread_messages_profile_pk,
                    unread_messages__count__gt=0,
                )
                .distinct()
            )

        return queryset
