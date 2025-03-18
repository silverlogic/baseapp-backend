import django_filters
import swapper
from django.db.models import Q

from baseapp_core.graphql import get_pk_from_relay_id

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")


class ChatRoomFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_q")
    profile_id = django_filters.CharFilter(method="filter_profile_id")
    unread_messages = django_filters.BooleanFilter(method="filter_unread_messages")
    archived = django_filters.BooleanFilter(method="filter_archived")

    order_by = django_filters.OrderingFilter(fields=(("created", "created"),))

    class Meta:
        model = ChatRoom
        fields = ["q", "order_by"]

    def filter_q(self, queryset, name, value):
        if not value:
            return queryset

        try:
            user_profile_id = self.request.user.current_profile.pk
        except AttributeError:
            user_profile_id = None

        return queryset.filter(
            (Q(is_group=True) & Q(title__icontains=value))
            | (
                Q(is_group=False)
                & Q(participants__profile__name__icontains=value)
                & (
                    Q(participants__profile_id__lt=user_profile_id)
                    | Q(participants__profile_id__gt=user_profile_id)
                )
            )
        ).distinct()

    def filter_profile_id(self, queryset, name, value):
        pk = get_pk_from_relay_id(value)
        return queryset.filter(participants__profile_id=pk)

    def filter_unread_messages(self, queryset, name, value):
        if value:
            profile_id = self.data.get("profile_id", None)
            try:
                user_profile = self.request.user.current_profile
            except AttributeError:
                return queryset.none()

            unread_messages_profile_pk = (
                get_pk_from_relay_id(profile_id) if profile_id else user_profile.pk
            )

            return (
                queryset.prefetch_related("unread_messages")
                .filter(
                    Q(unread_messages__profile_id=unread_messages_profile_pk),
                    Q(unread_messages__count__gt=0) | Q(unread_messages__marked_unread=True),
                )
                .distinct()
            )

        return queryset

    def filter_archived(self, queryset, name, value):
        try:
            user_profile = self.request.user.current_profile
        except AttributeError:
            return queryset.none()

        return queryset.filter(
            participants__profile_id=user_profile.pk, participants__has_archived_room=value
        ).distinct()
