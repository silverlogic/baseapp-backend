import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import swapper
from constance import config
from django.apps import apps
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from baseapp_core.graphql import get_pk_from_relay_id

from .utils import (
    STRIPE_LIVE_SUBSCRIPTION_STATUSES,
    StripeService,
    stripe_field,
    stripe_id,
)

if TYPE_CHECKING:
    import stripe

    from .models import BaseCustomer, BaseSubscription

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

    def get_default_price(self, obj: "stripe.Product | dict[str, Any]") -> "str | dict | None":
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
    client_secret = serializers.SerializerMethodField()

    def get_client_secret(self, instance: "stripe.Invoice") -> "str | None":
        # list_invoices() requests no expansion, so Stripe sends payment_intent as a bare
        # id string and calling .get() on it raised AttributeError, 500ing the whole list.
        # Guarded rather than expanded: no consumer reads this field, so paying for
        # expand=["data.payment_intent"] on every invoice page would buy nothing.
        payment_intent = stripe_field(instance, "payment_intent")
        if not isinstance(payment_intent, dict):
            return None
        return payment_intent.get("client_secret")

    def to_representation(self, instance: "stripe.Invoice") -> dict:
        representation = super().to_representation(instance)
        lines = representation.get("lines", {}).get("data", [])
        representation["lines"] = StripeInvoiceLineSerializer(lines, many=True).data
        if "created" in representation and representation["created"] is not None:
            representation["created"] = datetime.fromtimestamp(
                representation["created"], tz=timezone.utc
            )
        if (
            "webhooks_delivered_at" in representation
            and representation["webhooks_delivered_at"] is not None
        ):
            representation["webhooks_delivered_at"] = datetime.fromtimestamp(
                representation["webhooks_delivered_at"], tz=timezone.utc
            )
        return representation


class StripeSubscriptionSerializer(serializers.Serializer):
    entity_id = serializers.CharField(required=False)
    price_id = serializers.CharField(
        help_text=_("Stripe price ID"), required=False, write_only=True
    )
    allow_incomplete = serializers.BooleanField(default=False, write_only=True)
    payment_method_id = serializers.CharField(required=False, write_only=True)
    billing_details = serializers.DictField(required=False, write_only=True)
    default_payment_method = serializers.CharField(required=False)
    id = serializers.CharField(read_only=True)
    client_secret = serializers.SerializerMethodField()
    latest_invoice = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    product = serializers.SerializerMethodField()
    current_period_end = serializers.DateTimeField(read_only=True)
    upcoming_invoice = serializers.SerializerMethodField()

    def validate_create(self, data: dict[str, Any]) -> dict:
        entity_id = data["entity_id"]
        if not entity_id:
            raise serializers.ValidationError({"entity_id": [_("This field is required.")]})
        if isinstance(entity_id, str):
            # "" is what get_pk_from_relay_id answers for a non-relay id; querying on
            # it raises ValueError from the pk field rather than returning nothing.
            entity_id = get_pk_from_relay_id(entity_id) or None
        customer = (
            Customer.objects.filter(entity_id=entity_id).first() if entity_id is not None else None
        )
        if not customer:
            raise serializers.ValidationError({"entity_id": [_("Customer not found.")]})
        data["customer"] = customer
        price_id = data.get("price_id")
        if not price_id:
            raise serializers.ValidationError({"price_id": [_("This field is required.")]})
        stripe_service = StripeService()
        try:
            price = stripe_service.retrieve_price(price_id)
            if not price:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            _("Price not found: %(price_id)s") % {"price_id": price_id}
                        ]
                    }
                )
            new_product_id = stripe_id(stripe_field(price, "product"))
            subscriptions = stripe_service.list_subscriptions(
                customer.remote_customer_id, status="all"
            )
            # .data is only Stripe's first page (10 by default), so a customer with
            # more subscriptions than that could slip a duplicate past this check.
            for subscription in subscriptions.auto_paging_iter():
                if subscription["status"] in STRIPE_ACTIVE_SUBSCRIPTION_STATUSES:
                    sub_price = subscription["items"]["data"][0]["price"]
                    sub_product_id = stripe_id(stripe_field(sub_price, "product"))
                    if sub_product_id == new_product_id:
                        raise serializers.ValidationError(
                            {
                                "non_field_errors": [
                                    _(
                                        "You already have an active subscription to "
                                        "this product. Current subscription is on "
                                        "price: %(price_id)s"
                                    )
                                    % {"price_id": sub_price["id"]}
                                ]
                            }
                        )
            return data
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        _("An error occurred while checking existing subscriptions.")
                    ]
                }
            )

    def validate_update(self, instance: "BaseSubscription", data: dict[str, Any]) -> dict:
        try:
            customer = Customer.objects.filter(id=instance.customer_id).first()
            if not customer:
                raise serializers.ValidationError({"customer_id": [_("Customer not found.")]})
            stripe_service = StripeService()
            # Materialized: both checks below iterate this, and a generator would be
            # exhausted by the first, failing the second for every caller that sends
            # both a payment_method_id and a default_payment_method.
            payment_methods = list(
                stripe_service.list_payment_methods(customer.remote_customer_id).auto_paging_iter()
            )
            payment_method_id = data.get("payment_method_id")
            default_payment_method = data.get("default_payment_method")
            if payment_method_id and not any(
                pm["id"] == payment_method_id for pm in payment_methods
            ):
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            _("The provided payment method ID does not belong to the customer.")
                        ]
                    }
                )
            if default_payment_method and not any(
                pm["id"] == default_payment_method for pm in payment_methods
            ):
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            _("The provided payment method ID does not belong to the customer.")
                        ]
                    }
                )
            current_subscription = stripe_service.retrieve_subscription(
                instance.remote_subscription_id
            )
            data["current_subscription"] = current_subscription
        except Exception as e:
            logger.exception(f"Failed to validate payment method: {str(e)}")
            raise serializers.ValidationError(
                {"non_field_errors": [_("Invalid payment method ID.")]}
            )
        return data

    def create(self, validated_data: dict[str, Any]) -> "stripe.Subscription":
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
                    logger.exception(f"Failed to update payment method: {str(e)}")
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
            raise serializers.ValidationError(
                {"non_field_errors": [_("Failed to create subscription")]}
            )

    def update(
        self, instance: "BaseSubscription", validated_data: dict[str, Any]
    ) -> "stripe.Subscription":
        data = self.validate_update(instance, validated_data)
        default_payment_method = data.get("default_payment_method")
        payment_method_id = data.get("payment_method_id")
        billing_details = data.get("billing_details")
        if billing_details:
            billing_details = data.pop("billing_details")
        current_subscription = data.pop("current_subscription")
        stripe_service = StripeService()
        billing_details_updated = False
        try:
            fields = {}
            if default_payment_method:
                fields["default_payment_method"] = default_payment_method
            else:
                if payment_method_id and billing_details:
                    # Not swallowed any more: logging and continuing meant a rejected
                    # billing update still answered 200, telling the caller the new
                    # address was saved when Stripe had refused it.
                    stripe_service.update_payment_method(
                        payment_method_id, billing_details=billing_details
                    )
                    billing_details_updated = True
                price_id = data.get("price_id")
                if price_id:
                    # Swap in one call so the customer is never briefly on both plans
                    # or on none.
                    current_item_id = (
                        current_subscription.get("items", {}).get("data", [{}])[0].get("id")
                    )
                    fields["items"] = [
                        {"id": current_item_id, "deleted": True},
                        {"price": price_id},
                    ]
                if (
                    payment_method_id
                    and current_subscription.default_payment_method != payment_method_id
                ):
                    fields["default_payment_method"] = payment_method_id
            if not fields:
                if billing_details_updated:
                    # Stripe has already accepted the billing change, so reporting
                    # "nothing to update" would fail a request whose work landed.
                    return current_subscription
                raise serializers.ValidationError({"non_field_errors": [_("Nothing to update.")]})
            subscription = stripe_service.update_subscription(
                instance.remote_subscription_id, **fields
            )
            return subscription
        except serializers.ValidationError:
            # Re-raised as-is: the generic handler below used to rewrite "Nothing to
            # update." into a Stripe failure the caller never actually hit.
            raise
        except Exception as e:
            logger.exception("Failed to update subscription in Stripe: %s", e)
            raise serializers.ValidationError(
                {"non_field_errors": [_("Failed to update subscription in Stripe")]}
            )

    def get_latest_invoice(self, instance: "stripe.Subscription") -> "str | dict | None":
        latest_invoice = stripe_field(instance, "latest_invoice")
        # Subscription.create and Subscription.modify ask for no expansion, so Stripe
        # sends the bare id. Declaring this as a nested StripeInvoiceSerializer made
        # DRF serialize that string as an invoice, which 500'd every plan change.
        # Mirrors how get_default_price already answers for products.
        if latest_invoice is None or isinstance(latest_invoice, str):
            return latest_invoice
        return StripeInvoiceSerializer(latest_invoice).data

    def get_client_secret(self, instance: "stripe.Subscription") -> "str | None":
        latest_invoice = instance.get("latest_invoice", {})
        if isinstance(latest_invoice, dict):
            payment_intent = latest_invoice.get("payment_intent", {})
            if isinstance(payment_intent, dict):
                client_secret = payment_intent.get("client_secret")
                return client_secret
        return None

    def get_product(self, instance: "stripe.Subscription") -> "str | dict | None":
        items = instance.get("items", {}).get("data", [])
        if items:
            price = stripe_field(items[0], "price")
            product = stripe_field(price, "product")
            if product:
                if isinstance(product, dict):
                    return StripeProductSerializer(product).data
                return product
        return None

    def get_upcoming_invoice(self, instance: "stripe.Subscription") -> dict:
        upcoming_invoice = instance.get("upcoming_invoice") or {}
        if not upcoming_invoice:
            return upcoming_invoice
        # Stripe leaves this null when collection is not automatic, and
        # fromtimestamp(None) is a TypeError - a 500 on an ordinary subscription read.
        # Returning a new dict rather than writing back into the instance.
        next_attempt = upcoming_invoice.get("next_payment_attempt")
        return {
            "amount_due": upcoming_invoice.get("amount_due"),
            "next_payment_attempt": (
                datetime.fromtimestamp(next_attempt, tz=timezone.utc) if next_attempt else None
            ),
        }

    def to_representation(self, instance: "stripe.Subscription") -> dict:
        instance_period_end = instance.get("current_period_end")
        if instance_period_end:
            instance["current_period_end"] = datetime.fromtimestamp(
                instance_period_end, tz=timezone.utc
            )
        representation = super().to_representation(instance)
        return representation


class StripeSubscriptionCustomerListSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    products_ids = serializers.SerializerMethodField()

    def get_products_ids(self, instance: "stripe.Subscription") -> "list[str | None]":
        items = instance.get("items", {}).get("data", [])
        return [stripe_id(stripe_field(stripe_field(item, "price"), "product")) for item in items]


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

    def validate(self, data: dict[str, Any]) -> dict:
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
                        {
                            "non_field_errors": [
                                _("Entity does not have a target with an email field.")
                            ]
                        }
                    )
            else:
                if not entity.email:
                    raise serializers.ValidationError(
                        {"non_field_errors": [_("Entity does not have an email field.")]}
                    )
            data["entity"] = entity
        return data

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> "BaseCustomer":
        entity = validated_data.pop("entity")
        entity_model_name = config.STRIPE_CUSTOMER_ENTITY_MODEL
        email = entity.target.email if entity_model_name == "profiles.Profile" else entity.email
        try:
            stripe_customer = StripeService().create_customer(
                email=email, metadata={"entity_id": entity.id}
            )
        except Exception as e:
            logger.exception(e)
            raise serializers.ValidationError(
                {"non_field_errors": [_("Failed to create customer")]}
            )
        customer = Customer.objects.create(
            entity=entity,
            remote_customer_id=stripe_customer.get("id"),
        )
        return customer

    def get_subscriptions(self, instance: "BaseCustomer") -> list:
        # Asking Stripe for "active" alone excluded trialing, past_due, unpaid and
        # incomplete, so the settings page told a customer mid-failed-renewal that they
        # had no subscription - and incomplete is the state checkout itself produces.
        # The status filter takes one value or "all", so the set is narrowed here.
        # Paged rather than reading .data: with "all", canceled rows can fill page one.
        stripe_subscriptions = StripeService().list_subscriptions(
            instance.remote_customer_id, status="all"
        )
        live = [
            subscription
            for subscription in stripe_subscriptions.auto_paging_iter()
            if stripe_field(subscription, "status") in STRIPE_LIVE_SUBSCRIPTION_STATUSES
        ]
        return StripeSubscriptionCustomerListSerializer(live, many=True).data


class EntityIdSerializer(serializers.Serializer):
    """The `entity_id` a create request bills.

    Both create routes authorize the entity before anything is created, which means
    reading it before the body serializer runs. Validating it here keeps that read out
    of the viewsets and gives DRF's own "required"/"blank" errors.
    """

    entity_id = serializers.CharField()


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

    def create(self, validated_data: dict[str, Any]) -> dict:
        stripe_service = StripeService()
        try:
            setup_intent = stripe_service.create_setup_intent(
                customer_id=self.context.get("customer").remote_customer_id,
            )
            return {"id": setup_intent["id"], "client_secret": setup_intent["client_secret"]}
        except Exception as e:
            logger.exception(f"Failed to create setup intent: {str(e)}")
            # Without the raise this returned None and the view answered 201, so a
            # failed Stripe call looked like a card was added.
            raise serializers.ValidationError(
                {"non_field_errors": [_("An internal error has occurred. Please try again later.")]}
            ) from e

    def update(self, validated_data: dict[str, Any]) -> "stripe.Customer | stripe.PaymentMethod":
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
                raise serializers.ValidationError(
                    {"non_field_errors": [_("Failed to update payment method")]}
                )
        else:
            # `pk` identifies which card to modify - forwarding it as a Stripe field
            # made every billing update a 500 on an unknown parameter. billing_details
            # is declared read_only so the response keeps its nested shape, which means
            # the input has to be read off initial_data.
            fields = {k: v for k, v in validated_data.items() if k != "pk"}
            billing_details = self.initial_data.get("billing_details")
            if billing_details:
                fields["billing_details"] = billing_details
            if not fields:
                raise serializers.ValidationError({"non_field_errors": [_("Nothing to update.")]})
            try:
                # Returned, not discarded: answering None made the view send a 200 with
                # an empty body, which responseEquals rejects outright.
                return stripe_service.update_payment_method(payment_method_id, **fields)
            except Exception as e:
                logger.exception(e)
                raise serializers.ValidationError(
                    {"non_field_errors": [_("Failed to update payment method")]}
                )
