from rest_framework import serializers


class StripeWebhookSerializer(serializers.Serializer):
    id = serializers.CharField()
    object = serializers.CharField()
