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


class CustomerNotFound(Exception):
    pass


class CustomerOwnershipError(Exception):
    pass


class CustomerUpdateError(Exception):
    pass


class PaymentIntendNotFound(Exception):
    pass


class PaymentMethodNotFound(Exception):
    pass


class PaymentMethodUpdateError(Exception):
    pass


class PaymentMethodDeletionError(Exception):
    pass


class SetupIntentCreationError(Exception):
    pass


class PriceRetrievalError(Exception):
    pass


class InvoiceNotFound(Exception):
    pass


class SubscriptionCreationError(Exception):
    pass


class SubscriptionNotFound(Exception):
    pass


class StripeService:
    def __init__(
        self,
        api_key=settings.STRIPE_SECRET_KEY,
        api_version=getattr(settings, "STRIPE_API_VERSION", "2025-02-24.acacia"),
    ):
        stripe.api_key = api_key
        stripe.api_version = api_version

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
            raise CustomerNotFound("Error retrieving customer in Stripe")

    def update_customer(self, customer_id, **kwargs):
        try:
            return stripe.Customer.modify(customer_id, **kwargs)
        except Exception as e:
            logger.exception(e)
            raise CustomerUpdateError("Error updating customer in Stripe")

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
            raise SubscriptionCreationError("Error creating subscription in Stripe")

    def create_incomplete_subscription(
        self, customer_id, price_id, payment_method_id=None, product_id=None
    ):
        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                default_payment_method=payment_method_id,
                payment_behavior="default_incomplete",
                payment_settings={"save_default_payment_method": "on_subscription"},
                expand=["latest_invoice.payment_intent"],
                metadata={"product_id": product_id} if product_id else None,
            )
            client_secret = (
                subscription.get("latest_invoice", {})
                .get("payment_intent", {})
                .get("client_secret", None)
            )
            subscription["client_secret"] = client_secret
            return subscription
        except Exception as e:
            logger.exception(e)
            raise SubscriptionCreationError("Error creating subscription intent in Stripe")

    def retrieve_subscription(self, subscription_id):
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except Exception as e:
            if "No such subscription" in str(e):
                return None
            logger.exception(e)
            raise SubscriptionNotFound("Error retrieving subscription in Stripe")
        customer = subscription.get("customer", None)
        try:
            upcoming_invoice = stripe.Invoice.upcoming(customer=customer)
            subscription["upcoming_invoice"] = {
                "amount_due": upcoming_invoice.amount_due,
                "next_payment_attempt": upcoming_invoice.next_payment_attempt,
            }
        except Exception as e:
            logger.warning(f"Failed to retrieve upcoming invoice for customer {customer}: {str(e)}")
        return subscription

    def list_subscriptions(self, customer_id, **kwargs) -> list:
        try:
            subscriptions = stripe.Subscription.list(customer=customer_id, **kwargs)
            return subscriptions
        except Exception as e:
            if "No such customer" in str(e):
                return []
            logger.exception(e)
            raise SubscriptionNotFound("Error retrieving subscriptions for customer in Stripe")

    def delete_subscription(self, subscription_id):
        try:
            response = stripe.Subscription.cancel(subscription_id)
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

    def retrieve_product(self, product_id):
        try:
            product = stripe.Product.retrieve(product_id, expand=["default_price"])
            return product
        except stripe.error.InvalidRequestError as e:
            logger.error(f"Failed to retrieve product: {str(e)}")
            return None
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error: {str(e)}")
            return None

    def retrieve_payment_method(self, payment_method_id):
        try:
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            return payment_method
        except Exception as e:
            logger.exception(e)
            raise PaymentMethodNotFound("Error retrieving payment method in Stripe")

    def list_payment_methods(self, customer_id, type="card"):
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type=type,
            )
            return payment_methods.data
        except Exception as e:
            logger.exception(e)
            raise CustomerNotFound("Customer not found in Stripe")

    def get_customer_payment_methods(self, remote_customer_id):
        customer = self.retrieve_customer(remote_customer_id)
        if not customer:
            raise CustomerNotFound("Customer not found in Stripe")
        default_payment_method = customer.get("invoice_settings", {}).get("default_payment_method")
        try:
            payment_methods = self.list_payment_methods(remote_customer_id)
            if default_payment_method:
                for pm in payment_methods:
                    if pm.id == default_payment_method:
                        pm["is_default"] = True
                        break
            else:
                for pm in payment_methods:
                    pm["is_default"] = False
            return payment_methods
        except Exception as e:
            logger.exception(e)
            raise PaymentIntendNotFound("Failed to retrieve payment methods")

    def update_payment_method(self, payment_method_id, **kwargs):
        try:
            return stripe.PaymentMethod.modify(
                payment_method_id,
                **kwargs,
            )
        except Exception as e:
            logger.exception(e)
            raise PaymentMethodUpdateError("Error updating payment method in Stripe")

    def delete_payment_method(self, payment_method_id, customer_id, is_default=False):
        try:
            if is_default:
                stripe.Customer.modify(
                    customer_id, invoice_settings={"default_payment_method": None}
                )
            response = stripe.PaymentMethod.detach(payment_method_id)
            return response
        except Exception as e:
            logger.exception(e)
            raise PaymentMethodDeletionError("Error deleting payment method in Stripe")

    def get_upcoming_invoice(self, customer_id):
        try:
            invoice = stripe.Invoice.upcoming(customer=customer_id)
            return invoice
        except Exception as e:
            logger.exception(e)
            raise InvoiceNotFound("Error retrieving upcoming invoice in Stripe")

    def get_payment_intent(self, payment_intent_id):
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            return payment_intent
        except stripe.error.InvalidRequestError as e:
            if "No such PaymentIntent" in str(e):
                return None
            logger.error(f"Failed to retrieve PaymentIntent: {str(e)}")
            raise PaymentIntendNotFound("Error retrieving PaymentIntent in Stripe")
        except Exception as e:
            logger.exception(e)
            raise PaymentIntendNotFound("Error retrieving PaymentIntent in Stripe")

    def create_setup_intent(self, customer_id):
        try:
            setup_intent = stripe.SetupIntent.create(
                customer=customer_id,
                payment_method_types=["card"],
            )
            return setup_intent
        except Exception as e:
            logger.exception(e)
            raise SetupIntentCreationError("Error creating SetupIntent in Stripe")

    def retrieve_price(self, price_id):
        try:
            price = stripe.Price.retrieve(price_id, expand=["product"])
            return price
        except stripe.error.InvalidRequestError as e:
            if "No such price" in str(e):
                logger.error(f"Price not found: {price_id}")
                return None
            logger.error(f"Invalid request for price {price_id}: {str(e)}")
            return None
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error retrieving price {price_id}: {str(e)}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error retrieving price {price_id}: {str(e)}")
            raise PriceRetrievalError(f"Error retrieving price from Stripe: {str(e)}")

    def checkCustomerIdForUser(self, remote_customer_id, user):
        try:
            customer = self.retrieve_customer(remote_customer_id)
            if not customer:
                logger.warning(f"Customer {remote_customer_id} not found in Stripe.")
                return False
            linked_customer = Customer.objects.filter(
                remote_customer_id=remote_customer_id, entity_id=user.id
            ).first()
            if linked_customer:
                return True
            else:
                logger.warning(f"Customer {remote_customer_id} does not belong to user {user.id}.")
                return False
        except Exception as e:
            logger.exception(f"Error checking customer ID for user: {e}")
            raise CustomerOwnershipError("Error verifying customer ownership.")

    def update_subscription(self, subscription_id, **kwargs):

        try:
            subscription = stripe.Subscription.modify(subscription_id, **kwargs)
            return subscription
        except stripe.error.InvalidRequestError as e:
            if "No such subscription" in str(e):
                raise SubscriptionNotFound("Subscription not found in Stripe")
            logger.error(f"Invalid request: {str(e)}")
            raise
        except Exception as e:
            logger.exception(e)
            raise SubscriptionCreationError("Error updating subscription in Stripe")
