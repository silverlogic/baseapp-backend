import swapper
from django.contrib import admin

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
Message = swapper.load_model("baseapp_chats", "Message")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")


class ChatRoomParticipantInline(admin.TabularInline):
    model = ChatRoomParticipant
    extra = 0


@admin.register(ChatRoomParticipant)
class ChatRoomParticipantAdmin(admin.ModelAdmin):
    list_display = ("profile", "room", "role")
    list_filter = ["created", "role"]
    search_fields = ["profile", "room"]


class MessageStatusInline(admin.TabularInline):
    model = MessageStatus
    extra = 0


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("profile", "verb", "action_object", "room", "timesince")
    list_filter = ["verb"]
    search_fields = ["content", "profile", "action_object", "room"]
    inlines = [MessageStatusInline]


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ("room", "title", "is_group")
    search_fields = ["room"]
    inlines = [ChatRoomParticipantInline]

    def room(self, obj):
        return obj.__str__()
