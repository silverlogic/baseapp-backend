import stripe
from django.conf import settings
from djstripe.models import Customer, PaymentIntent, PaymentMethod

if settings.STRIPE_LIVE_MODE:
    stripe.api_key = settings.STRIPE_LIVE_SECRET_KEY
else:
    stripe.api_key = settings.STRIPE_TEST_SECRET_KEY


def get_customer_payment_methods(customer_id, payment_type="card"):
    return stripe.PaymentMethod.list(
        customer=customer_id,
        type=payment_type,
    )


def edit_payment_method(payment_method_id, data):
    return stripe.PaymentMethod.modify(
        payment_method_id,
        billing_details={
            "address": {
                "city": data["city"],
                "country": data["country"],
                "line1": data["line1"],
                "line2": data["line2"],
                "postal_code": data["postal_code"],
                "state": data["state"],
            },
            "name": data["name"],
        },
        card={
            "exp_month": data["exp_month"],
            "exp_year": data["exp_year"],
        },
    )


def make_another_default_payment_method(customer_id, payment_method_id):
    data = stripe.Customer.modify(
        customer_id,
        invoice_settings={"default_payment_method": payment_method_id},
    )
    # example of sync to DJ-stripe
    Customer.sync_from_stripe_data(data)
    return data


def update_subscription(subscription, price, is_upgrade):
    if is_upgrade:
        data = stripe.Subscription.modify(
            subscription.id,
            items=[
                {
                    "id": subscription.items.all()[0].id,
                    "price": price.id,
                }
            ],
            billing_cycle_anchor="now",
            proration_behavior="create_prorations",
        )
    else:
        data = stripe.Subscription.modify(
            subscription.id,
            items=[
                {
                    "id": subscription.items.all()[0].id,
                    "price": price.id,
                }
            ],
            proration_behavior="none",
        )

    data_item = data["items"]["data"][0]

    return data, data_item


def delete_payment_method(payment_method_id, customer_id):
    # payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
    data = stripe.PaymentMethod.detach(payment_method_id)
    PaymentMethod.sync_from_stripe_data(data)
    return data


#  being used for tests but example since using stripe.js
def attach_payment_method(data):
    payment_method = stripe.PaymentMethod.create(
        type="card",
        card={
            "number": data["card_number"],
            "exp_month": data["exp_month"],
            "exp_year": data["exp_year"],
            "cvc": data["cvc"],
        },
        billing_details={
            "address": {
                "city": data["address_city"],
                "country": data["address_country"],
                "line1": data["address_line1"],
                "line2": data["address_line2"],
                "postal_code": data["address_zip"],
                "state": data["address_state"],
            },
            "name": data["address_state"],
        },
    )

    return payment_method


# not being used but example if not using react stripe
def create_source(card):
    source = stripe.Source.create(type="card", card=card)
    return source


def add_metadata_to_payment_method(payment_method_id, source_id):
    data = stripe.PaymentMethod.modify(payment_method_id, metadata={"source_id": source_id})
    PaymentMethod.sync_from_stripe_data(data)


def create_payment_intent(product, request, validated_data):
    payment_method = validated_data["payment_method"]
    currency = settings.STRIPE_DEFAULT_CURRENCY
    customer = stripe.PaymentMethod.retrieve(payment_method).customer

    params = {
        "payment_method_types": ["card"],
        "currency": currency,
        "customer": customer,
    }
    params.update(product.stripe_payment_intent_params(request, validated_data))

    intent = stripe.PaymentIntent.create(**params)
    PaymentIntent.sync_from_stripe_data(intent)
    intent = stripe.PaymentIntent.confirm(intent.id, payment_method=payment_method)
    return PaymentIntent.sync_from_stripe_data(intent)
