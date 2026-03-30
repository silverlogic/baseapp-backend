import logging

import swapper
from constance import config
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import serializers

from baseapp_payments.utils import StripeService

logger = logging.getLogger(__name__)

Customer = swapper.load_model("baseapp_payments", "Customer")


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

    @transaction.atomic
    def create(self, validated_data):
        customer_entity_model = config.STRIPE_CUSTOMER_ENTITY_MODEL
        user = validated_data.pop("user")
        entity_model = apps.get_model(customer_entity_model)
        if customer_entity_model == "profiles.Profile":
            entity = entity_model.objects.get(owner=user.id)
        else:
            entity = entity_model.objects.get(profile_id=user.id)
        try:
            stripe_customer = StripeService().create_customer(email=user.email)
            if isinstance(stripe_customer, dict) and "id" in stripe_customer:
                customer = Customer.objects.create(
                    entity=entity, remote_customer_id=stripe_customer.get("id")
                )
            else:
                customer = Customer.objects.create(
                    entity=entity, remote_customer_id=stripe_customer.id
                )
        except IntegrityError:
            raise serializers.ValidationError("Customer already exists for this entity.")
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError("Failed to create customer")
        return customer

    def to_representation(self, instance):
        if isinstance(instance, Customer):
            representation = super().to_representation(instance)
            representation["entity_type"] = instance.entity._meta.model_name
            representation["entity_id"] = instance.entity.id
            return representation
        else:
            return super().to_representation(instance)
