from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers


def get_content_type_by_natural_key(value):
    value = value.lower()

    try:
        app_label, model_name = value.split(".")
    except ValueError:
        raise serializers.ValidationError(
            {
                "target_content_type": [
                    "Wrong natural key, please use the format app_label.ModelName"
                ]
            }
        )

    try:
        return ContentType.objects.get_by_natural_key(app_label, model_name)
    except ContentType.DoesNotExist:
        raise serializers.ValidationError({"target_content_type": ["Content type not found"]})
