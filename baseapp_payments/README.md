# BaseApp Payments

Integrates Stripe with your Django project over Django REST Framework. It exposes API endpoints to manage Stripe customers, subscriptions, products and payment methods, and a webhook endpoint that keeps your local `Customer` / `Subscription` records in sync with Stripe.

Unlike most BaseApp packages, payments is a **REST** surface (no GraphQL). It follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin and contributes its URL patterns through the registry — you do not wire the router by hand.

## How to install

Install the package with `pip install baseapp-backend[payments]`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

The package registers itself as a plugin (see `baseapp_payments.plugin:PaymentsPlugin`).

1. Add `baseapp_payments` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_payments",
    # ...
]
```

2. Add your Stripe credentials to settings:

```python
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
```

## Customer Integration

A Customer represents any entity (such as a User, Organization, or any model with an email attribute) that will be billed through Stripe.

By default we have configured to work with profiles, meaning it will get the email through `profile.target.email`, but you can also use other models if the model has a email field, simply changing the STRIPE_CUSTOMER_ENTITY_MODEL to your chosen model. Be aware that this model must have a ContentType though.

With a provided `entity_id`, the `StripeCustomerSerializer` creates a customer in Stripe and our Customer model links them via the `remote_customer_id` and `entity_id`.

## Subscription Management

The Subscription model stores Stripe subscription details including:

`customer` (a foreign key to the Customer that owns it)
`remote_subscription_id`

## Creating a Subscription

To create a subscription, use the `payments/stripe/subscriptions/` (assuming your route is registered at `payments/`) endpoint. A validation will check that no active subscription exists for the same product and price id, to reduce duplicate subscriptions, and then creates a new subscription through the Stripe API. It returns the new `remote_subscription_id` upon success.

## Configure URL Patterns

The plugin contributes its routes via `v1_urlpatterns`, so your project's `urls.py` composes them through the registry - there is no manual `include` of the payments router:

```python
from baseapp_core.plugins import plugin_registry

v1_urlpatterns = [
    # ... project v1 patterns ...
    *plugin_registry.get_all_v1_urlpatterns(),
]

urlpatterns = [
    path("v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
    # ...
]
```

This mounts the payments router under `v1/payments/` (see [API endpoints](#api-endpoints)).

4. Define the concrete `Customer` / `Subscription` models (see [models](#models)) and point the swapper settings at them:

```python
BASEAPP_PAYMENTS_CUSTOMER_MODEL = "payments.Customer"
BASEAPP_PAYMENTS_SUBSCRIPTION_MODEL = "payments.Subscription"
```

## Customer entity model

A `Customer` links any local entity (a `Profile`, `User`, `Organization`, or any model with an `email`) to its Stripe customer record via `remote_customer_id`. Which model is treated as the billable entity is a **Constance** setting (changeable at runtime), defaulting to `profiles.Profile`:

```python
# Constance config — default "profiles.Profile"
STRIPE_CUSTOMER_ENTITY_MODEL = "profiles.Profile"
```

When a customer is created (via the API or the `customer.created` webhook), the entity is resolved from this model and linked to the Stripe customer.

## Models

`BaseCustomer` and `BaseSubscription` are abstract + swappable, and the package ships **no** concrete models or migrations — your project must subclass them and point the swapper settings at the concrete models (see [How to develop](#how-to-develop)).

| Abstract | Concrete reference | Purpose |
|---|---|---|
| `BaseCustomer` | `Customer` | Generic-FK `entity` (the billable model) + `remote_customer_id`. |
| `BaseSubscription` | `Subscription` | `customer` (FK to the concrete Customer) + `remote_subscription_id`. |

> **Important:** `BaseCustomer.save()` requires the concrete model to declare `tracker = FieldTracker(["entity"])` (from `model_utils`) — it uses the tracker to populate `entity_type` / `entity_id` when the generic `entity` changes, and raises a `RuntimeError` if it's missing.

## API Endpoints

All routes are mounted under `v1/payments/`. **The router is `DefaultRouter(trailing_slash=True)`, so every path ends in `/`** - an unslashed request does not resolve and only survives via Django's `APPEND_SLASH` redirect, which drops the body on writes.

Authenticated endpoints require `IsAuthenticated` plus an object permission; the webhook is unauthenticated (verified by Stripe signature instead).

| Method & path | Action |
|---|---|
| `GET v1/payments/stripe/subscriptions/?entity_id=...` | List an entity's subscriptions (`?status=` widens past the default `active`). |
| `POST v1/payments/stripe/subscriptions/` | Create a subscription (rejects a duplicate active subscription for the same product/price). |
| `GET v1/payments/stripe/subscriptions/{remote_subscription_id}/` | Retrieve subscription details from Stripe. |
| `PATCH v1/payments/stripe/subscriptions/{remote_subscription_id}/` | Update a subscription. |
| `DELETE v1/payments/stripe/subscriptions/{remote_subscription_id}/` | Cancel a subscription. |
| `POST v1/payments/stripe/customers/` | Create a customer. |
| `GET v1/payments/stripe/customers/{entity_id}/` | Retrieve a customer by entity relay id, or `me` for the current user. |
| `GET v1/payments/stripe/customers/{entity_id}/invoices/` | List the customer's invoices (paginated). |
| `GET v1/payments/stripe/customers/{entity_id}/payment-methods/` | List the customer's payment methods. |
| `POST v1/payments/stripe/customers/{entity_id}/payment-methods/` | Create a `SetupIntent` to attach a payment method. |
| `PUT v1/payments/stripe/customers/{entity_id}/payment-methods/{payment_method_id}/` | Update a payment method. |
| `DELETE v1/payments/stripe/customers/{entity_id}/payment-methods/{payment_method_id}/` | Detach a payment method. |
| `GET v1/payments/stripe/products/` | List Stripe products. |
| `GET v1/payments/stripe/products/{product_id}/` | Retrieve a product. |
| `POST v1/payments/stripe/webhooks/` | Stripe webhook receiver. |

Payment-method and invoice routes are nested under the customer, so the entity in the URL is authorized through `DRFCustomerPermissions` before Stripe is called.

## Stripe webhooks

`StripeWebhookViewset` verifies the Stripe signature against `STRIPE_WEBHOOK_SECRET` and dispatches to `StripeWebhookHandler`, which handles:

- `customer.created` — create the local `Customer` (resolving the entity from `STRIPE_CUSTOMER_ENTITY_MODEL`).
- `customer.deleted` — delete the local `Customer`.
- `customer.subscription.created` — create the local `Subscription`.
- `customer.subscription.deleted` — delete the local `Subscription`.

### Stripe dashboard configuration

**Production:** In your [Stripe Dashboard](https://dashboard.stripe.com) → **Developers → Webhooks → Add endpoint**, point the endpoint at `https://yourdomain.com/v1/payments/stripe/webhooks`, subscribe to at least the four events above, then copy the **Signing secret** into `STRIPE_WEBHOOK_SECRET`.

**Local development:** Use the [Stripe CLI](https://stripe.com/docs/stripe-cli):

```bash
stripe login
stripe listen --forward-to localhost:8000/v1/payments/stripe/webhooks
```

The CLI prints a `whsec_...` secret — set it as `STRIPE_WEBHOOK_SECRET` locally.

## StripeService

`StripeService` (in `baseapp_payments.utils`) encapsulates all Stripe API calls — customers, subscriptions (including incomplete subscriptions), products, payment methods, setup/payment intents, prices and invoices — and is used internally by the serializers, viewsets and webhook handler so Stripe communication stays in one place.

## Admin

Both swapped models are registered in the Django admin (`CustomerAdmin`, `SubscriptionAdmin`) with `remote_*` ids read-only, for easy inspection of Stripe-linked records.

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).

### Prerequisites when activating `baseapp_payments`

Because the models are abstract + swappable with no concrete models shipped, create a local app (we suggest `apps/payments/`) implementing the concrete models — note the required `FieldTracker` on `Customer`:

```python
from model_utils import FieldTracker

from baseapp_payments.models import BaseCustomer, BaseSubscription


class Customer(BaseCustomer):
    tracker = FieldTracker(["entity"])

    class Meta(BaseCustomer.Meta):
        pass


class Subscription(BaseSubscription):
    class Meta(BaseSubscription.Meta):
        pass
```

Then point swapper at them and run `makemigrations` / `migrate`:

```python
BASEAPP_PAYMENTS_CUSTOMER_MODEL = "payments.Customer"
BASEAPP_PAYMENTS_SUBSCRIPTION_MODEL = "payments.Subscription"
```
