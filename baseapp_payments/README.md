# BaseApp Payments - Django

This app integrates Stripe with your Django project using Django REST Framework.

It provides API endpoints to manage Stripe customers and subscriptions, while also handling webhooks for real-time synchronization between Stripe and your system.

## Install the Package

Add the package to your `requirements/base.txt`:

```bash
baseapp-payments==0.16.1
```

## Setup Stripe Credentials

Add your Stripe credentials to your settings/base.py:

```python
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
```

## Customer Integration

A Customer represents any entity (such as a User, Organization, or any model with an email attribute) that will be billed through Stripe. You can configure the customer entity model by setting the corresponding value in your settings:

```python
# This can be updated in the Constance config
STRIPE_CUSTOMER_ENTITY_MODEL = "profiles.Profile"
```

When a customer is created via the API, the `StripeCustomerSerializer` will use the authenticated user (or a provided `user_id`) to retrieve the appropriate entity from your customer model. This entity is then linked to the Stripe customer record via the `remote_customer_id`.

## Subscription Management

The Subscription model stores Stripe subscription details including:

`remote_customer_id`
`remote_subscription_id`

## Creating a Subscription

To create a subscription, use the `payments/stripe/customer/` (assuming your route is registered at `payments/`) endpoint. A validation will check that no active subscription exists for the same product and price id, to redduce duplicate subscriptions, and then creates a new subscription through the Stripe API. It returns the new `remote_subscription_id` upon success.

## Configure URL Patterns

Include the payments router in your URL configuration. For example, in your main `urls.py`:

```python
from django.urls import include, path
from baseapp_payments.router import payments_router

urlpatterns = [
# ... your other URL patterns
path('payments/', include(payments_router.urls)),
]
```

## API Endpoints

The following endpoints are provided via the payments router:

`POST payments/stripe/`: Create a new Stripe subscription.
`GET payments/stripe/{remote_subscription_id}`: Retrieve subscription details from Stripe.
`DELETE payments/stripe/`: Delete a subscription.
`GET/POST payments/stripe/customer/`: Retrieve or create a customer.
`GET payments/stripe/products/`: List available Stripe products.
`POST payments/stripe/webhook/`: Endpoint for handling Stripe webhook events.

## Stripe Webhooks

The app includes a `StripeWebhookHandler` to process various Stripe events:

`customer.created`: Automatically creates a new customer in your system.
`customer.deleted`: Deletes the corresponding customer record.
`customer.subscription.created`: Creates a new subscription record.
`customer.subscription.deleted`: Deletes a subscription record.
These handlers ensure that any changes in Stripe are reflected in your local database, keeping your system in sync.

## Stripe Service

The StripeService class encapsulates all interactions with the Stripe API. It provides methods to:

Create, retrieve, and delete customers
Create, retrieve, and delete subscriptions
List subscriptions and products
This service is used internally by serializers, viewsets, and the webhook handler to standardize communication with Stripe.

## Admin Integration

Both the Customer and Subscription models are registered with the Django admin interface for easy management of Stripe-related data:

```python
from django.contrib import admin
import swapper
Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
list_display = ("entity", "remote_customer_id")
search_fields = ("entity", "remote_customer_id")
readonly_fields = ("remote_customer_id",)

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
list_display = ("id", "remote_customer_id", "remote_subscription_id")
search_fields = ("remote_customer_id", "remote_subscription_id")
readonly_fields = ("remote_subscription_id", "remote_customer_id")
```
