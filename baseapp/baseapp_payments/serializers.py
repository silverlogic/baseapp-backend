import logging

from constance import config
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework import serializers

from .models import Customer
from .utils import StripeService

logger = logging.getLogger(__name__)


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

    def validate(self, data):
        customer_id = data["remote_customer_id"]
        price_id = data["price_id"]

        subscriptions = StripeService().list_subscriptions(customer_id, status="all")
        for subscription in subscriptions:
            if (
                subscription["status"] in {"active", "incomplete"}
                and subscription["items"]["data"][0]["price"]["id"] == price_id
            ):
                raise serializers.ValidationError(
                    "A subscription with this price already exists for this customer."
                )

        return data

    def create(self, validated_data):
        customer_id = validated_data["remote_customer_id"]
        price_id = validated_data["price_id"]
        allow_incomplete = validated_data.get("allow_incomplete", False)
        payment_method_id = validated_data.get("payment_method_id")
        billing_details = validated_data.get("billing_details")

        try:
            if payment_method_id and billing_details:
                try:
                    StripeService().update_payment_method_billing_details(
                        payment_method_id, billing_details
                    )
                except Exception as e:
                    logger.error(f"Failed to update payment method: {str(e)}")
                    # Continue with subscription creation even if billing update fails

            kwargs = {"customer_id": customer_id, "price_id": price_id}
            if payment_method_id:
                kwargs["payment_method_id"] = payment_method_id

            if allow_incomplete:
                subscription = StripeService().create_subscription_intent(**kwargs)
                result = {
                    "remote_subscription_id": subscription["id"],
                    "client_secret": subscription["latest_invoice"]["payment_intent"][
                        "client_secret"
                    ],
                    "invoice_id": subscription["latest_invoice"]["id"],
                }
            else:
                subscription = StripeService().create_subscription(**kwargs)
                result = {"remote_subscription_id": subscription.id}

            return result

        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError("Failed to create subscription")


class StripeCustomerSerializer(serializers.Serializer):
    remote_customer_id = serializers.ReadOnlyField()
    entity_type = serializers.ReadOnlyField()
    entity_id = serializers.ReadOnlyField()
    user_id = serializers.CharField(required=False)

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
