import logging

import stripe
import swapper
from constance import config
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from django.http import JsonResponse

from .models import Subscription

logger = logging.getLogger(__name__)

Customer = swapper.load_model("baseapp_payments", "Customer")


class StripeWebhookHandler:
    def __init__(self):
        self.EVENT_HANDLERS = {
            "customer.created": self.customer_created,
            "customer.deleted": self.customer_deleted,
            "customer.subscription.created": self.subscription_created,
            "customer.subscription.deleted": self.subscription_deleted,
        }

    @staticmethod
    def customer_created(event):
        customer_entity_model = config.STRIPE_CUSTOMER_ENTITY_MODEL
        customer_data = event["data"]["object"]
        try:
            user = get_user_model().objects.get(email=customer_data["email"])
            if customer_entity_model != "profiles.Profile":
                entity_model = apps.get_model(customer_entity_model)
                entity = entity_model.objects.get(profile_id=user.id)
            else:
                entity_model = apps.get_model(customer_entity_model)
                entity = entity_model.objects.get(owner=user.id)
            Customer.objects.create(entity=entity, remote_customer_id=customer_data["id"])
            return JsonResponse({"status": "success"}, status=200)
        except IntegrityError:
            return JsonResponse({"status": "success"}, status=200)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=500)

    @staticmethod
    def customer_deleted(event):
        customer_data = event["data"]["object"]
        try:
            Customer.objects.filter(remote_customer_id=customer_data["id"]).delete()
            return JsonResponse({"status": "success"}, status=200)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=500)

    @staticmethod
    def subscription_created(event):
        subscription_data = event["data"]["object"]
        try:
            Subscription.objects.create(
                remote_customer_id=subscription_data["customer"],
                remote_subscription_id=subscription_data["id"],
            )
            return JsonResponse({"status": "success"}, status=200)
        except IntegrityError:
            return JsonResponse({"status": "success"}, status=200)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=500)

    @staticmethod
    def subscription_deleted(event):
        subscription_data = event["data"]["object"]
        try:
            Subscription.objects.filter(remote_subscription_id=subscription_data["id"]).delete()
            return JsonResponse({"status": "success"}, status=200)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=500)

    def webhook_handler(self, request, secret):
        payload = request.body
        sig_header = request.META["HTTP_STRIPE_SIGNATURE"]
        endpoint_secret = secret

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except ValueError as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=400)
        except stripe.error.SignatureVerificationError as e:
            logger.exception(e)
            return JsonResponse({"error": "Error"}, status=400)

        event_type = event["type"]
        handler = self.EVENT_HANDLERS.get(event_type)

        if handler:
            return handler(event)
        else:
            # if event is not handled, return 200 so stripe doesn't keep resending
            return JsonResponse({"status": "success"}, status=200)


class StripeService:
    def __init__(
        self,
        api_key=settings.STRIPE_SECRET_KEY,
    ):
        stripe.api_key = api_key

    def create_customer(self, email=None):
        try:
            if email is None:
                return stripe.Customer.create()
            return stripe.Customer.create(email=email)
        except Exception as e:
            logger.exception(e)
            raise Exception("Error creating customer in Stripe")

    def retrieve_customer(self, customer_id):
        try:
            customer = stripe.Customer.retrieve(customer_id)
            return customer
        except stripe.error.InvalidRequestError as e:
            if "No such customer" in str(e):
                return None
        except Exception as e:
            logger.exception(e)
            raise Exception("Error retrieving customer in Stripe")

    def delete_customer(self, customer_id):
        try:
            response = stripe.Customer.delete(customer_id)
            return response
        except stripe.error.InvalidRequestError as e:
            if "No such customer" in str(e):
                return None
        except Exception as e:
            logger.exception(e)
            raise Exception("Error deleting customer in Stripe")

    def create_subscription(self, customer_id, price_id):
        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
            )
            return subscription
        except Exception as e:
            logger.exception(e)
            raise Exception("Error creating subscription in Stripe")

    def retrieve_subscription(self, subscription_id):
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return subscription
        except Exception as e:
            if "No such subscription" in str(e):
                return None
            logger.exception(e)
            raise Exception("Error retrieving subscription in Stripe")

    def list_subscriptions(self, customer_id, **kwargs):
        try:
            subscriptions = stripe.Subscription.list(customer=customer_id, **kwargs)
            return subscriptions
        except Exception as e:
            if "No such customer" in str(e):
                return None
            logger.exception(e)
            raise Exception("Error retrieving subscriptions for customer in Stripe")

    def delete_subscription(self, subscription_id):
        try:
            response = stripe.Subscription.delete(subscription_id)
            return response
        except Exception as e:
            if "No such subscription" in str(e):
                return None
            logger.exception(e)
            raise Exception("Error deleting subscription in Stripe")

    def list_products(self, **kwargs):
        try:
            products = stripe.Product.list(**kwargs)
            return products
        except Exception as e:
            logger.exception(e)
            raise Exception("Error retrieving products in Stripe")
