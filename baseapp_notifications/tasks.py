from celery import shared_task
from django.apps import apps
from django.utils.encoding import force_str


@shared_task
def send_push_notification(
    user_id, extra=None, push_title=None, push_description=None, level=None, **kwargs
) -> None:
    if not apps.is_installed("push_notifications"):
        return

    from push_notifications.models import (
        APNSDevice,
        GCMDevice,
        WebPushDevice,
        WNSDevice,
    )

    if not push_description:
        raise Exception("push_description is required")

    # Plain-text body shared by every device type. Built up front so users who only have
    # Windows or Web devices still get a message.
    message = force_str(push_description)

    # send messages to all Apple devices
    apple_devices = APNSDevice.objects.filter(user__id=user_id)
    if apple_devices:
        apple_message = message
        if push_title:
            apple_message = {"title": force_str(push_title), "body": message}
        apple_devices.send_message(message=apple_message, extra=extra)

    # send messages to all Android devices
    android_devices = GCMDevice.objects.filter(user__id=user_id)
    if android_devices:
        if push_title:
            android_devices.send_message(message, title=push_title, extra=extra)
        else:
            android_devices.send_message(message=message, extra=extra)

    # TO DO: send messages to all Windows devices
    windows_devices = WNSDevice.objects.filter(user__id=user_id)
    if windows_devices:
        windows_devices.send_message(message=message, extra=extra)

    # TO DO: send messages to all Web devices
    web_devices = WebPushDevice.objects.filter(user__id=user_id)
    if web_devices:
        web_devices.send_message(message=message, extra=extra)
