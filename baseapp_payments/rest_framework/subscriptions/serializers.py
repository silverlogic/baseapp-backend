import logging

import swapper
from rest_framework import serializers

from baseapp_payments.utils import StripeService

logger = logging.getLogger(__name__)

STRIPE_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "incomplete", "past_due"}

Customer = swapper.load_model("baseapp_payments", "Customer")


class StripeSubscriptionSerializer(serializers.Serializer):
    remote_customer_id = serializers.CharField(help_text="Stripe customer ID")
    price_id = serializers.CharField(help_text="Stripe price ID")
    allow_incomplete = serializers.BooleanField(
        default=False,
    )
    payment_method_id = serializers.CharField(
        required=False,
    )
    billing_details = serializers.DictField(
        required=False,
    )
    remote_subscription_id = serializers.CharField(read_only=True)
    client_secret = serializers.CharField(read_only=True)
    invoice_id = serializers.CharField(read_only=True)
    latest_invoice = serializers.DictField(read_only=True)

    def validate(self, data):
        customer_id = data.get("remote_customer_id")
        if "remote_customer_id" in data and not customer_id:
            raise serializers.ValidationError({"remote_customer_id": "This field is required."})
        price_id = data.get("price_id")
        if "price_id" in data and not price_id:
            raise serializers.ValidationError({"price_id": "This field is required."})
        user = self.context.get("request").user
        stripe_service = StripeService()
        if not stripe_service.checkCustomerIdForUser(customer_id, user=user):
            raise serializers.ValidationError(
                "The provided customer ID does not belong to the authenticated user."
            )
        price_id = data["price_id"]
        try:
            price = stripe_service.retrieve_price(price_id)
            if not price:
                raise serializers.ValidationError(f"Price not found: {price_id}")
            new_product_id = price.get("product").get("id", None)
            subscriptions = stripe_service.list_subscriptions(customer_id, status="all")
            for subscription in subscriptions:
                if subscription["status"] in STRIPE_ACTIVE_SUBSCRIPTION_STATUSES:
                    sub_price = subscription["items"]["data"][0]["price"]
                    sub_product_id = sub_price.get("product")
                    if sub_product_id == new_product_id:
                        raise serializers.ValidationError(
                            f"You already have an active subscription to this product. "
                            f"Current subscription is on price: {sub_price['id']}"
                        )
            return data
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError(
                "An error occurred while checking existing subscriptions."
            )

    def create(self, validated_data):
        customer_id = validated_data["remote_customer_id"]
        price_id = validated_data["price_id"]
        allow_incomplete = validated_data.get("allow_incomplete", False)
        payment_method_id = validated_data.get("payment_method_id")
        billing_details = validated_data.get("billing_details")
        stripe_service = StripeService()
        try:
            if payment_method_id and billing_details:
                try:
                    stripe_service.update_payment_method(
                        payment_method_id, billing_details=billing_details
                    )
                except Exception as e:
                    logger.error(f"Failed to update payment method: {str(e)}")
                    # Continue with subscription creation even if billing update fails
            kwargs = {"customer_id": customer_id, "price_id": price_id}
            if payment_method_id:
                kwargs["payment_method_id"] = payment_method_id
            if allow_incomplete:
                subscription = stripe_service.create_incomplete_subscription(**kwargs)
                result = {
                    "remote_subscription_id": subscription["id"],
                    "client_secret": subscription["client_secret"],
                    "invoice_id": subscription["latest_invoice"]["id"],
                }
            else:
                subscription = stripe_service.create_subscription(**kwargs)
                result = {"remote_subscription_id": subscription.id}
            return result
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError("Failed to create subscription")


class StripeSubscriptionPatchSerializer(serializers.Serializer):
    default_payment_method = serializers.CharField(required=False)
    remote_customer_id = serializers.CharField(required=True)

    def validate_remote_customer_id(self, value):
        user = self.context.get("request").user
        if not StripeService().checkCustomerIdForUser(value, user=user):
            raise serializers.ValidationError(
                "The provided customer ID does not belong to the authenticated user."
            )
        return value

    def validate_default_payment_method(self, value):
        remote_customer_id = self.initial_data.get("remote_customer_id")
        try:
            payment_methods = StripeService().list_payment_methods(remote_customer_id)
            if not any(pm["id"] == value for pm in payment_methods):
                raise serializers.ValidationError(
                    "The provided payment method ID does not belong to the customer."
                )
        except Exception as e:
            logger.error(f"Failed to validate payment method: {str(e)}")
            raise serializers.ValidationError("Invalid payment method ID.")
        return value

    def update(self, instance, validated_data):
        if "remote_customer_id" in validated_data:
            validated_data.pop("remote_customer_id")
        try:
            StripeService().update_subscription(
                subscription_id=instance.remote_subscription_id, **validated_data
            )
        except Exception as e:
            logger.exception("Failed to update subscription in Stripe: %s", e)
            raise serializers.ValidationError("Failed to update subscription in Stripe")
        return instance
