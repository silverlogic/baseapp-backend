import logging

from constance import config
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework import serializers

from .models import Customer
from .utils import StripeService

logger = logging.getLogger(__name__)


STRIPE_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "incomplete", "past_due"}


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


class StripeCustomerSerializer(serializers.Serializer):
    remote_customer_id = serializers.ReadOnlyField()
    entity_type = serializers.ReadOnlyField()
    entity_id = serializers.ReadOnlyField()
    user_id = serializers.CharField(required=False)
    upcoming_invoice = serializers.DictField(read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id",
            "remote_customer_id",
            "entity_type",
            "entity_id",
        )

    def validate(self, data):
        if "user_id" in data:
            try:
                user = get_user_model().objects.get(id=data["user_id"])
                data["user"] = user
                return data
            except get_user_model().DoesNotExist:
                raise serializers.ValidationError("User does not exist.")
        user = self.context.get("request").user
        data["user"] = user
        return data

    def create(self, validated_data):
        customer_entity_model = config.STRIPE_CUSTOMER_ENTITY_MODEL
        user = validated_data.pop("user")

        if customer_entity_model == "profiles.Profile":
            entity_model = apps.get_model(customer_entity_model)
            entity = entity_model.objects.get(owner=user.id)
        else:
            entity_model = apps.get_model(customer_entity_model)
            entity = entity_model.objects.get(profile_id=user.id)

        try:
            customer = Customer.objects.create(entity=entity)
            stripe_customer = StripeService().create_customer(user.email)
            customer.remote_customer_id = stripe_customer.id
            customer.save()
        except IntegrityError:
            raise serializers.ValidationError("Customer already exists for this entity.")
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError("Failed to create customer")
        return customer

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["entity_type"] = instance.entity._meta.model_name
        representation["entity_id"] = instance.entity.id
        return representation


class StripeWebhookSerializer(serializers.Serializer):
    id = serializers.CharField()
    object = serializers.CharField()


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
