from rest_framework import serializers


class StripePriceSerializer(serializers.Serializer):
    id = serializers.CharField()
    currency = serializers.CharField()
    unit_amount = serializers.IntegerField()
    recurring = serializers.DictField()


class StripeProductSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True, required=False)
    active = serializers.BooleanField()
    default_price = StripePriceSerializer(allow_null=True)
    metadata = serializers.DictField(required=False)
    images = serializers.ListField(child=serializers.URLField(), required=False)
    marketing_features = serializers.ListField(
        read_only=True,
        child=serializers.DictField(),
    )
