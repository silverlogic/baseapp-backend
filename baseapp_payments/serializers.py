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
    remote_customer_id = serializers.CharField()
    price_id = serializers.CharField()
    remote_subscription_id = serializers.ReadOnlyField()

    def validate(self, data):
        try:
            price_id = data.get("price_id")
            subscriptions = StripeService().list_subscriptions(
                data["remote_customer_id"], status="active"
            )

            for subscription in subscriptions:
                existing_price_id = subscription["items"]["data"][0]["price"]["id"]
                if existing_price_id == price_id:
                    raise serializers.ValidationError(
                        "Active subscription matching this price_id already exists for this customer."
                    )
            remote_subscription_id = StripeService().create_subscription(
                data["remote_customer_id"], price_id
            )
            data["remote_subscription_id"] = remote_subscription_id.id
            return data
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
