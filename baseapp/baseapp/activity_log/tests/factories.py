import factory


class ChatRoomFactory(factory.django.DjangoModelFactory):
    created_by = factory.SubFactory("baseapp_core.tests.factories.UserFactory")

    class Meta:
        model = "baseapp_chats.ChatRoom"


class MessageFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory("baseapp_core.tests.factories.UserFactory")
    room = factory.SubFactory(ChatRoomFactory)

    class Meta:
        model = "baseapp_chats.Message"


class ChatRoomParticipantFactory(factory.django.DjangoModelFactory):
    room = factory.SubFactory(ChatRoomFactory)
    profile = factory.SubFactory("baseapp_profiles.tests.factories.ProfileFactory")

    class Meta:
        model = "baseapp_chats.ChatRoomParticipant"


class MessageStatusFactory(factory.django.DjangoModelFactory):
    message = factory.SubFactory(MessageFactory)
    profile = factory.SubFactory("baseapp_profiles.tests.factories.ProfileFactory")

    class Meta:
        model = "baseapp_chats.MessageStatus"
