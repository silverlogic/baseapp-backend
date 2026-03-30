import logging

from rest_framework import serializers

from baseapp_payments.utils import StripeService

logger = logging.getLogger(__name__)


class StripeCardSerializer(serializers.Serializer):
    brand = serializers.CharField(read_only=True)
    exp_month = serializers.IntegerField(read_only=True)
    exp_year = serializers.IntegerField(read_only=True)
    last4 = serializers.CharField(read_only=True)
    funding = serializers.CharField(read_only=True)


class StripeBillingDetailsSerializer(serializers.Serializer):
    name = serializers.CharField(read_only=True)
    address = serializers.DictField(read_only=True)
    email = serializers.EmailField(read_only=True, allow_null=True)
    phone = serializers.CharField(read_only=True, allow_null=True)


class StripePaymentMethodSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)
    billing_details = StripeBillingDetailsSerializer(read_only=True)
    card = StripeCardSerializer(read_only=True)
    created = serializers.IntegerField(read_only=True)
    customer = serializers.CharField(read_only=True)
    is_default = serializers.BooleanField(read_only=True, default=False)
    customer_id = serializers.CharField(write_only=True, required=False)
    client_secret = serializers.CharField(read_only=True)
    pk = serializers.CharField(write_only=True, required=False)
    default_payment_method_id = serializers.CharField(write_only=True, required=False)

    def create(self, validated_data):
        stripe_service = StripeService()
        customer_id = validated_data.get("customer_id")
        try:
            setup_intent = stripe_service.create_setup_intent(
                customer_id=customer_id,
            )
            return {"id": setup_intent["id"], "client_secret": setup_intent["client_secret"]}
        except Exception as e:
            logger.error(f"Failed to create setup intent: {str(e)}")
            serializers.ValidationError("An internal error has occurred. Please try again later.")

    def update(self, validated_data):
        stripe_service = StripeService()
        customer_id = validated_data.get("customer_id")
        default_payment_method_id = validated_data.get("default_payment_method_id")
        payment_method_id = validated_data.get("pk")
        if default_payment_method_id:
            try:
                resp = stripe_service.update_customer(
                    customer_id,
                    invoice_settings={"default_payment_method": default_payment_method_id},
                )
                return resp
            except Exception as e:
                logger.exception(e)
                raise serializers.ValidationError("Failed to update payment method")
        else:
            validated_data.pop("customer_id")
            try:
                stripe_service.update_payment_method(payment_method_id, **validated_data)
            except Exception as e:
                logger.exception(e)
                raise serializers.ValidationError("Failed to update payment method")
