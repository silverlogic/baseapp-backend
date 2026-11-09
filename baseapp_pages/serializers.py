import swapper
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import URLPath

Page = swapper.load_model("baseapp_pages", "Page")


class PageSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    url_path = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    body = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Page
        fields = ("user", "title", "body", "url_path")

    def validate_url_path(self, value: str) -> str:
        language = get_language()
        queryset = URLPath.objects.filter(
            Q(language=language) | Q(language__isnull=True), path=value
        )
        if self.instance:
            queryset = queryset.exclude(
                target_content_type=ContentType.objects.get_for_model(self.instance),
                target_object_id=self.instance.pk,
            )

        if queryset.exists():
            raise serializers.ValidationError(_("URL Path already being used"))

        return value

    def save(self, **kwargs) -> "Page":
        url_path = self.validated_data.pop("url_path", None)
        instance = super().save(**kwargs)
        language = get_language()
        if url_path:
            URLPath.objects.create(
                target=instance, path=url_path, language=language, is_active=True
            )
        return instance
