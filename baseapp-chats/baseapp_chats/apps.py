from django.apps import AppConfig


class ChatsConfig(AppConfig):
    default = True
    name = "baseapp_chats"
    verbose_name = "BaseApp Chats"
    default_auto_field = "django.db.models.BigAutoField"
