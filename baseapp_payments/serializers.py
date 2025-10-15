import logging
from datetime import datetime

import swapper
from constance import config
from django.apps import apps
from django.db import transaction
from rest_framework import serializers

from baseapp_core.graphql import get_pk_from_relay_id

from .utils import StripeService

logger = logging.getLogger(__name__)


STRIPE_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "incomplete", "past_due"}

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


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
    default_price = serializers.SerializerMethodField()
    metadata = serializers.DictField(required=False)
    images = serializers.ListField(child=serializers.URLField(), required=False)
    marketing_features = serializers.ListField(
        read_only=True,
        child=serializers.DictField(),
    )

    def get_default_price(self, obj):
        default_price = obj.get("default_price")
        if default_price is None:
            return None
        if isinstance(default_price, str):
            return default_price
        if isinstance(default_price, dict):
            return StripePriceSerializer(default_price).data
        return None


class StripeInvoiceLineSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    amount = serializers.IntegerField(read_only=True)
    description = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    type = serializers.CharField(read_only=True)
    price = StripePriceSerializer(read_only=True)


class StripeInvoiceSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    amount_due = serializers.IntegerField(read_only=True)
    amount_paid = serializers.IntegerField(read_only=True)
    amount_remaining = serializers.IntegerField(read_only=True)
    created = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    lines = serializers.DictField(read_only=True)
    metadata = serializers.DictField(read_only=True)
    hosted_invoice_url = serializers.URLField(read_only=True)
    webhooks_delivered_at = serializers.IntegerField(read_only=True)
    client_secret = serializers.CharField(read_only=True, source="get_client_secret")

    def get_client_secret(self, instance):
        return instance.get("payment_intent", {}).get("client_secret")

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        lines = representation.get("lines", {}).get("data", [])
        representation["lines"] = StripeInvoiceLineSerializer(lines, many=True).data
        if "created" in representation and representation["created"] is not None:
            representation["created"] = datetime.fromtimestamp(representation["created"])
        if (
            "webhooks_delivered_at" in representation
            and representation["webhooks_delivered_at"] is not None
        ):
            representation["webhooks_delivered_at"] = datetime.fromtimestamp(
                representation["webhooks_delivered_at"]
            )
        return representation


class StripeSubscriptionSerializer(serializers.Serializer):
    entity_id = serializers.CharField(required=False)
    price_id = serializers.CharField(help_text="Stripe price ID", required=False, write_only=True)
    allow_incomplete = serializers.BooleanField(default=False, write_only=True)
    payment_method_id = serializers.CharField(required=False, write_only=True)
    billing_details = serializers.DictField(required=False, write_only=True)
    default_payment_method = serializers.CharField(required=False, write_only=True)
    id = serializers.CharField(read_only=True)
    client_secret = serializers.SerializerMethodField()
    latest_invoice = StripeInvoiceSerializer(read_only=True)
    status = serializers.CharField(read_only=True)
    product = serializers.SerializerMethodField()
    current_period_end = serializers.DateTimeField(read_only=True)
    upcoming_invoice = serializers.SerializerMethodField()
    default_payment_method = serializers.CharField(read_only=True)

    def validate_create(self, data):
        entity_id = data["entity_id"]
        if not entity_id:
            raise serializers.ValidationError({"entity_id": "This field is required."})
        if isinstance(entity_id, str):
            entity_id = get_pk_from_relay_id(entity_id)
        customer = Customer.objects.filter(entity_id=entity_id).first()
        if not customer:
            raise serializers.ValidationError({"entity_id": "Customer not found."})
        data["customer"] = customer
        price_id = data.get("price_id")
        if not price_id:
            raise serializers.ValidationError({"price_id": "This field is required."})
        stripe_service = StripeService()
        try:
            price = stripe_service.retrieve_price(price_id)
            if not price:
                raise serializers.ValidationError(f"Price not found: {price_id}")
            new_product_id = price.get("product").get("id", None)
            subscriptions = stripe_service.list_subscriptions(
                customer.remote_customer_id, status="all"
            )
            for subscription in subscriptions.data:
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

    def validate_update(self, instance, data):
        try:
            customer = Customer.objects.filter(id=instance.customer_id).first()
            if not customer:
                raise serializers.ValidationError({"customer_id": "Customer not found."})
            stripe_service = StripeService()
            payment_methods = stripe_service.list_payment_methods(customer.remote_customer_id)
            payment_method_id = data.get("payment_method_id")
            default_payment_method = data.get("default_payment_method")
            if payment_method_id and not any(
                pm["id"] == payment_method_id for pm in payment_methods
            ):
                raise serializers.ValidationError(
                    "The provided payment method ID does not belong to the customer."
                )
            if default_payment_method and not any(
                pm["id"] == default_payment_method for pm in payment_methods
            ):
                raise serializers.ValidationError(
                    "The provided payment method ID does not belong to the customer."
                )
            current_subscription = stripe_service.retrieve_subscription(
                instance.remote_subscription_id
            )
            data["current_subscription"] = current_subscription
        except Exception as e:
            logger.error(f"Failed to validate payment method: {str(e)}")
            raise serializers.ValidationError("Invalid payment method ID.")
        return data

    def create(self, validated_data):
        data = self.validate_create(validated_data)
        customer = data["customer"]
        price_id = data["price_id"]
        allow_incomplete = data.get("allow_incomplete", False)
        payment_method_id = data.get("payment_method_id")
        billing_details = data.get("billing_details")
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
            kwargs = {"customer_id": customer.remote_customer_id, "price_id": price_id}
            if payment_method_id:
                kwargs["payment_method_id"] = payment_method_id
            if allow_incomplete:
                subscription = stripe_service.create_incomplete_subscription(**kwargs)
            else:
                subscription = stripe_service.create_subscription(**kwargs)
            Subscription.objects.create(
                customer=customer,
                remote_subscription_id=subscription.get("id"),
            )
            return subscription
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError("Failed to create subscription")

    def update(self, instance, validated_data):
        data = self.validate_update(
            instance, validated_data if validated_data else self.initial_data
        )
        default_payment_method = data.get("default_payment_method")
        payment_method_id = data.get("payment_method_id")
        if data.get("billing_details"):
            billing_details = data.pop("billing_details")
        current_subscription = data.pop("current_subscription")
        stripe_service = StripeService()
        try:
            if default_payment_method:
                fields = {"default_payment_method": default_payment_method}
            elif payment_method_id and billing_details:
                try:
                    stripe_service.update_payment_method(
                        payment_method_id, billing_details=billing_details
                    )
                except Exception as e:
                    logger.exception(f"Failed to update payment method: {str(e)}")
                    # Continue with subscription update even if billing update fails
                current_item_id = (
                    current_subscription.get("items", {}).get("data", [{}])[0].get("id")
                )
                fields = {
                    "items": [
                        {"id": current_item_id, "deleted": True},
                        {"price": data["price_id"]},
                    ]
                }
                if (
                    payment_method_id
                    and current_subscription.default_payment_method != payment_method_id
                ):
                    fields["default_payment_method"] = payment_method_id
            subscription = stripe_service.update_subscription(
                instance.remote_subscription_id, **fields
            )
            return subscription
        except Exception as e:
            logger.exception("Failed to update subscription in Stripe: %s", e)
            raise serializers.ValidationError("Failed to update subscription in Stripe")

    def get_client_secret(self, instance):
        latest_invoice = instance.get("latest_invoice", {})
        if isinstance(latest_invoice, dict):
            payment_intent = latest_invoice.get("payment_intent", {})
            if isinstance(payment_intent, dict):
                client_secret = payment_intent.get("client_secret")
                return client_secret
        return None

    def get_product(self, instance):
        items = instance.get("items", {}).get("data", [])
        if items:
            price = items[0].get("price", {})
            product = price.get("product")
            if product:
                if isinstance(product, dict):
                    return StripeProductSerializer(product).data
                return product
        return None

    def get_upcoming_invoice(self, instance):
        upcoming_invoice = instance.get("upcoming_invoice", {})
        if upcoming_invoice:
            upcoming_invoice["amount_due"] = upcoming_invoice.get("amount_due")
            upcoming_invoice["next_payment_attempt"] = datetime.fromtimestamp(
                upcoming_invoice.get("next_payment_attempt")
            )
        return upcoming_invoice

    def to_representation(self, instance):
        instance_period_end = instance.get("current_period_end")
        if instance_period_end:
            instance["current_period_end"] = datetime.fromtimestamp(instance_period_end)
        representation = super().to_representation(instance)
        return representation


class StripeSubscriptionCustomerListSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    products_ids = serializers.SerializerMethodField()

    def get_products_ids(self, instance):
        items = instance.get("items", {}).get("data", [])
        return [item.get("price", {}).get("product", {}) for item in items]


class StripeCustomerSerializer(serializers.Serializer):
    remote_customer_id = serializers.ReadOnlyField()
    entity_id = serializers.CharField(required=False)
    subscriptions = serializers.SerializerMethodField()
    upcoming_invoice = serializers.DictField(read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id",
            "remote_customer_id",
            "entity_id",
        )

    def validate(self, data):
        entity_id = data.get("entity_id")
        if entity_id:
            if isinstance(entity_id, str):
                entity_id = get_pk_from_relay_id(entity_id)
            entity_model_name = config.STRIPE_CUSTOMER_ENTITY_MODEL
            customer_model = apps.get_model(entity_model_name)
            entity = customer_model.objects.get(id=entity_id)
            if entity_model_name == "profiles.Profile":
                if not entity.target.email:
                    raise serializers.ValidationError(
                        "Entity does not have a target with an email field."
                    )
            else:
                if not entity.email:
                    raise serializers.ValidationError("Entity does not have an email field.")
            data["entity"] = entity
        return data

    @transaction.atomic
    def create(self, validated_data):
        entity = validated_data.pop("entity")
        entity_model_name = config.STRIPE_CUSTOMER_ENTITY_MODEL
        email = entity.target.email if entity_model_name == "profiles.Profile" else entity.email
        try:
            stripe_customer = StripeService().create_customer(
                email=email, metadata={"entity_id": entity.id}
            )
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError("Failed to create customer")
        customer = Customer.objects.create(
            entity=entity,
            remote_customer_id=stripe_customer.get("id"),
        )
        return customer

    def get_subscriptions(self, instance):
        stripe_subscriptions = StripeService().list_subscriptions(instance.remote_customer_id)
        return StripeSubscriptionCustomerListSerializer(stripe_subscriptions.data, many=True).data


class StripeWebhookSerializer(serializers.Serializer):
    id = serializers.CharField()
    object = serializers.CharField()


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
    is_default = serializers.BooleanField(read_only=True, default=False)
    client_secret = serializers.CharField(read_only=True)
    pk = serializers.CharField(write_only=True, required=False)
    default_payment_method_id = serializers.CharField(write_only=True, required=False)

    def create(self, validated_data):
        stripe_service = StripeService()
        try:
            setup_intent = stripe_service.create_setup_intent(
                customer_id=self.context.get("customer").remote_customer_id,
            )
            return {"id": setup_intent["id"], "client_secret": setup_intent["client_secret"]}
        except Exception as e:
            logger.error(f"Failed to create setup intent: {str(e)}")
            serializers.ValidationError("An internal error has occurred. Please try again later.")

    def update(self, validated_data):
        stripe_service = StripeService()
        default_payment_method_id = validated_data.get("default_payment_method_id")
        payment_method_id = validated_data.get("pk")
        if default_payment_method_id:
            try:
                resp = stripe_service.update_customer(
                    self.context.get("customer").remote_customer_id,
                    invoice_settings={"default_payment_method": default_payment_method_id},
                )
                return resp
            except Exception as e:
                logger.exception(e)
                raise serializers.ValidationError("Failed to update payment method")
        else:
            try:
                stripe_service.update_payment_method(payment_method_id, **validated_data)
            except Exception as e:
                logger.exception(e)
                raise serializers.ValidationError("Failed to update payment method")
