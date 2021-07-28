import importlib

from django.conf import settings

import swapper
from djstripe.models import Customer, PaymentMethod, Price, Product, Subscription, SubscriptionItem
from expander import ExpanderSerializerMixin
from rest_framework import serializers

from .utils import update_subscription

Plan = swapper.load_model("baseapp_payments", "Plan")


class EndSubscriptionSerializer(serializers.Serializer):
    feedback = serializers.CharField(required=True)


class CapturePaymentIntentSerializer(serializers.Serializer):
    payment_method_id = serializers.CharField(required=True)
    source_id = serializers.CharField(required=True)


class CapturePaymentEditSerializer(serializers.Serializer):
    payment_method_id = serializers.CharField(required=True)


class SubscribeCustomerSerializer(serializers.Serializer):
    plan = serializers.CharField(required=True)

    def validate(self, data):
        validated_data = super().validate(data)

        self.subscriber = self.context["request"].user.get_subscriber_from_request(
            self.context["request"]
        )

        self.customer, created = Customer.get_or_create(self.subscriber)
        customer_subscription_exits = (
            Subscription.objects.active().filter(customer=self.customer).exists()
        )
        if customer_subscription_exits:
            raise serializers.ValidationError({"Already Subscribed."})

        try:
            self.plan = Plan.objects.get(slug=validated_data["plan"])
        except Plan.DoesNotExist:
            raise serializers.ValidationError({"Plan not found."})

        return validated_data

    def save(self):
        subscription = self.customer.subscribe(plan=self.plan.price)
        self.subscriber.subscription_start_request(
            plan=self.plan,
            customer=self.customer,
            subscription=subscription,
            request=self.context["request"],
        )


class CancelSubscriptionSerializer(serializers.Serializer):
    def validate(self, data):
        validated_data = super().validate(data)

        self.subscriber = self.context["request"].user.get_subscriber_from_request(
            self.context["request"]
        )

        self.customer, created = Customer.get_or_create(self.subscriber)

        self.subscription = Subscription.objects.active().filter(customer=self.customer).first()

        if not self.subscription:
            raise serializers.ValidationError(
                {"non_field_errors": ["Customer has no Subscription."]}
            )

        return validated_data

    def save(self):
        subscription = self.subscription.cancel(at_period_end=True)
        self.subscriber.subscription_cancel_request(
            customer=self.customer, subscription=subscription, request=self.context["request"],
        )


class PaymentMethodSerializer(serializers.ModelSerializer):
    last4 = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethod
        fields = (
            "id",
            "created",
            "card",
            "last4",
        )

    def get_last4(self, obj):
        return obj.card["last4"]


class CustomerSerializer(ExpanderSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "id",
            "default_payment_method",
        )
        expandable_fields = {
            "default_payment_method": PaymentMethodSerializer,
        }


class UpdateSubscriptionSerializer(serializers.Serializer):
    plan = serializers.CharField()

    def validate(self, data):
        validated_data = super().validate(data)

        self.subscriber = self.context["request"].user.get_subscriber_from_request(
            self.context["request"]
        )

        self.customer, created = Customer.get_or_create(self.subscriber)

        self.subscription = Subscription.objects.active().filter(customer=self.customer).first()

        if not self.subscription:
            raise serializers.ValidationError(
                {"non_field_errors": ["Customer has no Subscription."]}
            )

        try:
            self.plan = Plan.objects.get(
                slug=validated_data["plan"], is_active=True, price__isnull=False
            )
        except Plan.DoestNotExist:
            raise serializers.ValidationError({"plan": ["Plan not found."]})

        return validated_data


class UpdatingSubscriptionSerializer(UpdateSubscriptionSerializer):
    def save(self):
        is_upgrade = (
            self.plan.price.unit_amount_decimal
            > self.subscription.items.all()[0].price.unit_amount_decimal
        )

        data, data_item = update_subscription(self.subscription, self.plan.price, is_upgrade)
        subscription = Subscription.sync_from_stripe_data(data)
        SubscriptionItem.sync_from_stripe_data(data_item)

        self.subscriber.subscription_update_request(
            customer=self.customer,
            subscription=subscription,
            plan=self.plan,
            is_upgrade=is_upgrade,
            request=self.context["request"],
        )

        PlanSerializer = get_serializer("PlanSerializer")

        return {
            "plan": PlanSerializer(self.plan, context=self.context).data,
            "is_upgrade": is_upgrade,
        }


class EditPaymentMethodSerializer(serializers.Serializer):
    payment_method_id = serializers.CharField(required=True)
    city = serializers.CharField(required=True)
    country = serializers.CharField(required=True)
    line1 = serializers.CharField(required=True)
    line2 = serializers.CharField(required=True, allow_blank=True)
    postal_code = serializers.CharField(required=True)
    state = serializers.CharField(required=True)
    name = serializers.CharField(required=True)
    exp_month = serializers.IntegerField(required=True)
    exp_year = serializers.IntegerField(required=True)


class PriceSerializer(ExpanderSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Price
        fields = (
            "id",
            "metadata",
            "description",
            "currency",
            "nickname",
            "recurring",
            "type",
            "unit_amount",
            "unit_amount_decimal",
            "billing_scheme",
            "lookup_key",
            "tiers",
            "tiers_mode",
            "transform_quantity",
        )


class ProductSerializer(ExpanderSerializerMixin, serializers.ModelSerializer):
    prices = PriceSerializer(many=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "metadata",
            "description",
            "name",
            "type",
            "attributes",
            "caption",
            "images",
            "package_dimensions",
            "url",
            "unit_label",
            "prices",
        )


class PlanSerializer(ExpanderSerializerMixin, serializers.ModelSerializer):
    price_amount = serializers.DecimalField(max_digits=19, decimal_places=12, source="price_amount")
    interval = serializers.CharField(source="interval")

    class Meta:
        model = Plan
        fields = (
            "id",
            "name",
            "slug",
            "price_amount",
            "interval",
            "is_active",
        )


def get_serializer(name):
    if settings.BASEAPP_PAYMENTS_PLAN_SERIALIZER:
        parts = settings.BASEAPP_PAYMENTS_PLAN_SERIALIZER.split(".")
        module_path = ".".join(parts[0:-1])
        class_name = parts[-1]
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    return PlanSerializer
