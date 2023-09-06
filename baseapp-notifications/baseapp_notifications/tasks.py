from celery import shared_task


@shared_task
def send_push_notification(user_id, data):
    # TO BE DONE
    # get user's device tokens and send to each of them
    # this function should be easy to override per project since
    # some projects might use different push notification services
    # like, expo, firebase, APN and so on
    pass
