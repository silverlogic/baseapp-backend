import factory
import swapper

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
Message = swapper.load_model("baseapp_chats", "Message")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")


class ChatRoomFactory(factory.django.DjangoModelFactory):
    created_by = factory.SubFactory("baseapp_core.tests.factories.UserFactory")
    created_by_profile = factory.LazyAttribute(
        lambda obj: (
            obj.created_by.profile
            if obj.created_by and hasattr(obj.created_by, "profile")
            else None
        )
    )

    class Meta:
        model = ChatRoom


class MessageFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory("baseapp_core.tests.factories.UserFactory")
    room = factory.SubFactory(ChatRoomFactory)

    class Meta:
        model = Message


class ChatRoomParticipantFactory(factory.django.DjangoModelFactory):
    room = factory.SubFactory(ChatRoomFactory)
    profile = factory.SubFactory("baseapp_profiles.tests.factories.ProfileFactory")

    class Meta:
        model = ChatRoomParticipant


class MessageStatusFactory(factory.django.DjangoModelFactory):
    message = factory.SubFactory(MessageFactory)
    profile = factory.SubFactory("baseapp_profiles.tests.factories.ProfileFactory")

    class Meta:
        model = MessageStatus
