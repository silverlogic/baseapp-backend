import swapper
from django.contrib.auth.backends import BaseBackend
from django.db import models

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
Message = swapper.load_model("baseapp_chats", "Message")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
Block = swapper.load_model("baseapp_blocks", "Block")
Profile = swapper.load_model("baseapp_profiles", "Profile")
profile_app_label = Profile._meta.app_label


class ChatsPermissionsBackend(BaseBackend):
    def can_add_chatroom(self, user_obj, obj):
        if isinstance(obj, dict):
            participants = obj["participants"]
            current_profile = obj["profile"]

            if len(participants) < 2:
                return False

            if current_profile:
                my_profile_ids = [current_profile.id]
            else:
                my_profile_ids = Profile.objects.filter_user_profiles(user_obj).values_list(
                    "id", flat=True
                )

            participant_profile_ids = [participant.pk for participant in participants]

            blocks_qs = Block.objects.filter(
                models.Q(actor_id__in=my_profile_ids, target_id__in=participant_profile_ids)
                | models.Q(actor_id__in=participant_profile_ids, target_id__in=my_profile_ids)
            )

            if blocks_qs.exists():
                return False

            return True

    def can_modify_chatroom(self, user_obj, obj):
        if isinstance(obj, dict):
            room = obj["room"]
            is_leaving_chatroom = obj["is_leaving_chatroom"]
            add_participants = obj["add_participants"]
            current_profile = obj["profile"]
            modify_image = obj["modify_image"]
            modify_title = obj["modify_title"]

            if not getattr(room, "is_group", False):
                return False

            chat_room_participant = ChatRoomParticipant.objects.filter(
                room=room, profile_id=current_profile.pk
            ).first()

            if not chat_room_participant:
                return False

            if (
                is_leaving_chatroom
                and not modify_image
                and not modify_title
                and not add_participants
            ):
                return True

            if chat_room_participant.role != ChatRoomParticipant.ChatRoomParticipantRoles.ADMIN:
                return False

            return True

    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_chats.add_chatroom" and user_obj.is_authenticated:
            return self.can_add_chatroom(user_obj, obj)
        if perm == "baseapp_chats.add_chatroom_with_profile":
            return user_obj.has_perm(f"{profile_app_label}.use_profile", obj)
        if perm == "baseapp_chats.delete_chat":
            if isinstance(obj, ChatRoom):
                return obj.user_id == user_obj.id or user_obj.has_perm(
                    f"{profile_app_label}.use_profile", obj.actor
                )
        if perm == "baseapp_chats.modify_chatroom":
            return self.can_modify_chatroom(user_obj, obj)
        if perm == "baseapp_chats.view_chatroom":
            my_profile_ids = Profile.objects.filter_user_profiles(user_obj).values_list(
                "id", flat=True
            )

            if not obj.participants.filter(models.Q(profile_id__in=my_profile_ids)).exists():
                return False

            participant_profile_ids = obj.participants.values_list("profile_id", flat=True)

            blocks_qs = Block.objects.filter(
                models.Q(actor_id__in=my_profile_ids, target_id__in=participant_profile_ids)
                | models.Q(actor_id__in=participant_profile_ids, target_id__in=my_profile_ids)
            )

            if blocks_qs.exists():
                return False

            return obj.participants.filter(profile_id__in=my_profile_ids).exists()

        if perm == "baseapp_chats.list_chatrooms":
            return obj.check_if_member(user_obj)

        if perm == "baseapp_chats.add_message":
            current_profile = obj["profile"]
            room = obj["room"]

            if current_profile:
                my_profile_ids = [current_profile.id]
            else:
                my_profile_ids = Profile.objects.filter_user_profiles(user_obj).values_list(
                    "id", flat=True
                )

            participant_profile_ids = room.participants.values_list("profile_id", flat=True)

            blocks_qs = Block.objects.filter(
                models.Q(actor_id__in=my_profile_ids, target_id__in=participant_profile_ids)
                | models.Q(actor_id__in=participant_profile_ids, target_id__in=my_profile_ids)
            )

            if blocks_qs.exists():
                return False

            return room.participants.filter(profile_id__in=my_profile_ids).exists()

        if (
            perm == "baseapp_chats.change_message" or perm == "baseapp_chats.delete_message"
        ) and user_obj.is_authenticated:
            profile = obj.get("profile", None)
            message = obj.get("message", None)
            if profile and message and isinstance(message, Message):
                return profile.id == message.profile.id

            return False
