import logging

import swapper
from celery import shared_task
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction

from baseapp_auth.anonymization import anonymize_activitylog
from baseapp_auth.emails import (
    send_anonymize_user_error_email,
    send_anonymize_user_success_email,
)


@shared_task
def anonymize_and_delete_user_task(user_id):
    User = get_user_model()
    user = User.objects.get(id=user_id)
    user_email = user.email

    try:
        with transaction.atomic():
            anonymize_activitylog(user)

            if apps.is_installed("baseapp_chats"):
                ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
                ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
                participant_qs = ChatRoomParticipant.objects.filter(profile__user=user)
                room_ids = list(participant_qs.values_list("room_id", flat=True).distinct())
                participant_qs.delete()

                for room_id in room_ids:
                    room = ChatRoom.objects.get(id=room_id)
                    room.participants_count = ChatRoomParticipant.objects.filter(room=room).count()
                    room.save(update_fields=["participants_count"])
            user.delete()
        send_anonymize_user_success_email(user_email)
    except Exception as e:
        logging.exception(e)
        send_anonymize_user_error_email(user_email)
        pass
