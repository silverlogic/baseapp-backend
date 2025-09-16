from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model

ModelAdmin = admin.ModelAdmin

try:
    from unfold import admin as unfold_admin

    ModelAdmin = unfold_admin.ModelAdmin
except ImportError:
    pass
from .models import BaseAPIKey

User = get_user_model()


class BaseAPIKeyAdmin(ModelAdmin):
    list_display = ("id", "user", "name", "encrypted_api_key", "is_expired")

    def is_expired(self, obj):
        return obj.is_expired

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None:  # Only set default for new objects
            form.base_fields["user"].initial = request.user
        return form

    def save_model(self, request, obj, form, change):
        if obj.pk is None:
            unencrypted_api_key = obj.__class__.objects.generate_unencrypted_api_key()
            encrypted_api_key = obj.__class__.objects.encrypt(unencrypted_value=unencrypted_api_key)
            self.message_user(request=request, message=f"Your API Key is {unencrypted_api_key}")
            obj.encrypted_api_key = encrypted_api_key

        super().save_model(request, obj, form, change)


for APIKeyClass in [
    ModelClass
    for ModelClass in apps.get_models()
    if isinstance(ModelClass, type)
    and issubclass(ModelClass, BaseAPIKey)
    and not ModelClass._meta.abstract
]:

    @admin.register(APIKeyClass)
    class _APIKeyAdmin(BaseAPIKeyAdmin[APIKeyClass]):
        pass
