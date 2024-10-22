import swapper
from django.contrib.auth.backends import BaseBackend
from django.db import models

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
Block = swapper.load_model("baseapp_blocks", "Block")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class ChatsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_chats.add_chatroom" and user_obj.is_authenticated:
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
        if perm == "baseapp_chats.add_chatroom_with_profile":
            return user_obj.has_perm("baseapp_profiles.use_profile", obj)
        if perm == "baseapp_chats.delete_chat":
            if isinstance(obj, ChatRoom):
                return obj.user_id == user_obj.id or user_obj.has_perm(
                    "baseapp_profiles.use_profile", obj.actor
                )
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
