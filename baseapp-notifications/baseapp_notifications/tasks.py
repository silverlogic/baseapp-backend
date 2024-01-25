from celery import shared_task
from django.utils.encoding import force_str


@shared_task
def send_push_notification(
    user_id, extra=None, push_title=None, push_description=None, level=None, **kwargs
):
    from push_notifications.models import (
        APNSDevice,
        GCMDevice,
        WebPushDevice,
        WNSDevice,
    )

    # send messages to all Apple devices
    apple_devices = APNSDevice.objects.filter(user__id=user_id)
    if apple_devices and push_title and push_description:
        message = {"title": force_str(push_title), "body": force_str(push_description)}
    if apple_devices:
        message = force_str(push_description)
    apple_devices.send_message(message=message, extra=extra)

    # send messages to all Android devices
    android_devices = GCMDevice.objects.filter(user__id=user_id)
    if android_devices and push_description:
        message = force_str(push_description)
        if push_title:
            extra.update({"title": force_str(push_title)})
    android_devices.send_message(message=message, extra=extra)

    # TO DO: send messages to all Windows devices
    windows_devices = WNSDevice.objects.filter(user__id=user_id)
    windows_devices.send_message(message=message, extra=extra)

    # TO DO: send messages to all Web devices
    web_devices = WebPushDevice.objects.filter(user__id=user_id)
    web_devices.send_message(message=message, extra=extra)
