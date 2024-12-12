from allauth.account.signals import email_confirmed
from django.dispatch import receiver
from baseapp_auth.emails import send_welcome_email

@receiver(email_confirmed)
def on_email_confirmed(email_address, **kwargs):
    """
    Signal handler that sends a welcome email when a new user confirms their email address.
    
    This function is triggered when a user confirms their email address. If the user has never
    logged in before (indicating they are a new user), it will send them a welcome email.
    
    Args:
        email_address: The EmailAddress instance that was confirmed
        **kwargs: Additional keyword arguments passed by the signal
    """
    user = email_address.user
    if user.last_login is None:
        send_welcome_email(user)
