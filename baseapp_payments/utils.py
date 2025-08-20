import logging

import stripe
import swapper
from constance import config
from django.apps import apps
from django.conf import settings
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
        customer_data = event["data"]["object"]
        try:
            existing_customer = Customer.objects.filter(
                remote_customer_id=customer_data["id"]
            ).first()
            if existing_customer:
                return JsonResponse({"status": "success"}, status=200)
            entity_id = customer_data["metadata"].get("entity_id")
            entity_model = apps.get_model(config.STRIPE_CUSTOMER_ENTITY_MODEL)
            entity = entity_model.objects.get(id=entity_id)
            Customer.objects.create(entity=entity, remote_customer_id=customer_data["id"])
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
            existing_subscription = Subscription.objects.filter(
                remote_subscription_id=subscription_data["id"]
            ).first()
            if existing_subscription:
                return JsonResponse({"status": "success"}, status=200)
            Subscription.objects.create(
                remote_customer_id=subscription_data["customer"],
                remote_subscription_id=subscription_data["id"],
            )
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


class CustomerCreationError(Exception):
    pass


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

    def create_customer(self, **kwargs):
        try:
            return stripe.Customer.create(**kwargs)
        except Exception as e:
            logger.exception(e)
            raise CustomerCreationError("Error creating customer in Stripe")

    def retrieve_customer(self, customer_id=None, email=None):
        try:
            if not customer_id and email:
                results = stripe.Customer.search(query=f"email:'{email}'")
                if results.data:
                    return results.data[0]
                else:
                    return None
            return stripe.Customer.retrieve(customer_id)
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

    def retrieve_subscription(self, subscription_id, **kwargs):
        try:
            subscription = stripe.Subscription.retrieve(subscription_id, **kwargs)
        except Exception as e:
            if "No such subscription" in str(e):
                return None
            logger.exception(e)
            raise SubscriptionNotFound("Error retrieving subscription in Stripe")
        customer = subscription.get("customer", None)
        try:
            upcoming_invoice = stripe.Invoice.create_preview(
                customer=customer,
                subscription=subscription_id
            )
            subscription["upcoming_invoice"] = {
                "amount_due": upcoming_invoice.amount_due,
                "next_payment_attempt": upcoming_invoice.next_payment_attempt,
            }
        except Exception as e:
            logger.warning(f"Failed to retrieve upcoming invoice for customer {customer}: {str(e)}")
        return subscription

    def list_subscriptions(self, customer_id, **kwargs) -> list:
        try:
            if "status" not in kwargs:
                kwargs["status"] = "active"
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
            if "active" not in kwargs:
                kwargs["active"] = True
            products = stripe.Product.list(**kwargs).auto_paging_iter()
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
                remote_customer_id=remote_customer_id, entity_id=user.profile.id
            ).first()
            if linked_customer:
                return True
            else:
                logger.warning(
                    f"Customer {remote_customer_id} does not belong to user {user.profile.id}."
                )
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

    def get_customer_invoices(self, customer_id):
        try:
            invoices = list(stripe.Invoice.list(customer=customer_id).auto_paging_iter())
            return invoices
        except Exception as e:
            logger.exception(e)
            raise InvoiceNotFound("Error retrieving invoices in Stripe")

# instance = {
#   "application": null,
#   "application_fee_percent": null,
#   "automatic_tax": {
#     "disabled_reason": null,
#     "enabled": false,
#     "liability": null
#   },
#   "billing_cycle_anchor": 1754492527,
#   "billing_cycle_anchor_config": null,
#   "billing_mode": {
#     "type": "classic"
#   },
#   "billing_thresholds": null,
#   "cancel_at": null,
#   "cancel_at_period_end": false,
#   "canceled_at": null,
#   "cancellation_details": {
#     "comment": null,
#     "feedback": null,
#     "reason": null
#   },
#   "collection_method": "charge_automatically",
#   "created": 1754492527,
#   "currency": "usd",
#   "current_period_end": 1757170927,
#   "current_period_start": 1754492527,
#   "customer": "cus_SoR2DTJQKyDSzl",
#   "days_until_due": null,
#   "default_payment_method": "pm_1Rt8qYGaogFGo7JVxZKhvirE",
#   "default_source": null,
#   "default_tax_rates": [],
#   "description": null,
#   "discount": null,
#   "discounts": [],
#   "ended_at": null,
#   "id": "sub_1Rt8qxGaogFGo7JVL26b3vCx",
#   "invoice_settings": {
#     "account_tax_ids": null,
#     "issuer": {
#       "type": "self"
#     }
#   },
#   "items": {
#     "data": [
#       {
#         "billing_thresholds": null,
#         "created": 1754492528,
#         "current_period_end": 1757170927,
#         "current_period_start": 1754492527,
#         "discounts": [],
#         "id": "si_SomPx0uZUrRoOt",
#         "metadata": {},
#         "object": "subscription_item",
#         "plan": {
#           "active": true,
#           "aggregate_usage": null,
#           "amount": 200,
#           "amount_decimal": "200",
#           "billing_scheme": "per_unit",
#           "created": 1746037445,
#           "currency": "usd",
#           "id": "price_1RJfIfGaogFGo7JVLSrZr8Sv",
#           "interval": "month",
#           "interval_count": 1,
#           "livemode": false,
#           "metadata": {},
#           "meter": null,
#           "nickname": null,
#           "object": "plan",
#           "product": "prod_SE7XS3bTXMDm9D",
#           "tiers_mode": null,
#           "transform_usage": null,
#           "trial_period_days": null,
#           "usage_type": "licensed"
#         },
#         "price": {
#           "active": true,
#           "billing_scheme": "per_unit",
#           "created": 1746037445,
#           "currency": "usd",
#           "custom_unit_amount": null,
#           "id": "price_1RJfIfGaogFGo7JVLSrZr8Sv",
#           "livemode": false,
#           "lookup_key": null,
#           "metadata": {},
#           "nickname": null,
#           "object": "price",
#           "product": {
#             "active": true,
#             "attributes": [],
#             "created": 1746037445,
#             "default_price": "price_1RJfIfGaogFGo7JVLSrZr8Sv",
#             "description": "Test",
#             "id": "prod_SE7XS3bTXMDm9D",
#             "images": [],
#             "livemode": false,
#             "marketing_features": [],
#             "metadata": {},
#             "name": "Product 2",
#             "object": "product",
#             "package_dimensions": null,
#             "shippable": null,
#             "statement_descriptor": null,
#             "tax_code": null,
#             "type": "service",
#             "unit_label": null,
#             "updated": 1746037446,
#             "url": null
#           },
#           "recurring": {
#             "aggregate_usage": null,
#             "interval": "month",
#             "interval_count": 1,
#             "meter": null,
#             "trial_period_days": null,
#             "usage_type": "licensed"
#           },
#           "tax_behavior": "unspecified",
#           "tiers_mode": null,
#           "transform_quantity": null,
#           "type": "recurring",
#           "unit_amount": 200,
#           "unit_amount_decimal": "200"
#         },
#         "quantity": 1,
#         "subscription": "sub_1Rt8qxGaogFGo7JVL26b3vCx",
#         "tax_rates": []
#       }
#     ],
#     "has_more": false,
#     "object": "list",
#     "total_count": 1,
#     "url": "/v1/subscription_items?subscription=sub_1Rt8qxGaogFGo7JVL26b3vCx"
#   },
#   "latest_invoice": {
#     "account_country": "US",
#     "account_name": "Default sandbox",
#     "account_tax_ids": null,
#     "amount_due": 200,
#     "amount_overpaid": 0,
#     "amount_paid": 200,
#     "amount_remaining": 0,
#     "amount_shipping": 0,
#     "application": null,
#     "application_fee_amount": null,
#     "attempt_count": 1,
#     "attempted": true,
#     "auto_advance": false,
#     "automatic_tax": {
#       "disabled_reason": null,
#       "enabled": false,
#       "liability": null,
#       "provider": null,
#       "status": null
#     },
#     "automatically_finalizes_at": null,
#     "billing_reason": "subscription_create",
#     "charge": "ch_3Rt8qyGaogFGo7JV0R3jb69k",
#     "collection_method": "charge_automatically",
#     "created": 1754492527,
#     "currency": "usd",
#     "custom_fields": null,
#     "customer": "cus_SoR2DTJQKyDSzl",
#     "customer_address": null,
#     "customer_email": "lb@tsl.io",
#     "customer_name": null,
#     "customer_phone": null,
#     "customer_shipping": null,
#     "customer_tax_exempt": "none",
#     "customer_tax_ids": [],
#     "default_payment_method": null,
#     "default_source": null,
#     "default_tax_rates": [],
#     "description": null,
#     "discount": null,
#     "discounts": [],
#     "due_date": null,
#     "effective_at": 1754492527,
#     "ending_balance": 0,
#     "footer": null,
#     "from_invoice": null,
#     "hosted_invoice_url": "https://invoice.stripe.com/i/acct_1R4NdRGaogFGo7JV/test_YWNjdF8xUjROZFJHYW9nRkdvN0pWLF9Tb21QS3FrRDlva3hXTDMzNklwV0R1ZjB6NWRLSm5LLDE0NjE3NDM5Mg02004WKSrvNk?s=ap",
#     "id": "in_1Rt8qxGaogFGo7JVLyQONIDN",
#     "invoice_pdf": "https://pay.stripe.com/invoice/acct_1R4NdRGaogFGo7JV/test_YWNjdF8xUjROZFJHYW9nRkdvN0pWLF9Tb21QS3FrRDlva3hXTDMzNklwV0R1ZjB6NWRLSm5LLDE0NjE3NDM5Mg02004WKSrvNk/pdf?s=ap",
#     "issuer": {
#       "type": "self"
#     },
#     "last_finalization_error": null,
#     "latest_revision": null,
#     "lines": {
#       "data": [
#         {
#           "amount": 200,
#           "amount_excluding_tax": 200,
#           "currency": "usd",
#           "description": "1 \u00d7 Product 2 (at $2.00 / month)",
#           "discount_amounts": [],
#           "discountable": true,
#           "discounts": [],
#           "id": "il_1Rt8qxGaogFGo7JVippoEPsk",
#           "invoice": "in_1Rt8qxGaogFGo7JVLyQONIDN",
#           "livemode": false,
#           "metadata": {},
#           "object": "line_item",
#           "parent": {
#             "invoice_item_details": null,
#             "subscription_item_details": {
#               "invoice_item": null,
#               "proration": false,
#               "proration_details": {
#                 "credited_items": null
#               },
#               "subscription": "sub_1Rt8qxGaogFGo7JVL26b3vCx",
#               "subscription_item": "si_SomPx0uZUrRoOt"
#             },
#             "type": "subscription_item_details"
#           },
#           "period": {
#             "end": 1757170927,
#             "start": 1754492527
#           },
#           "plan": {
#             "active": true,
#             "aggregate_usage": null,
#             "amount": 200,
#             "amount_decimal": "200",
#             "billing_scheme": "per_unit",
#             "created": 1746037445,
#             "currency": "usd",
#             "id": "price_1RJfIfGaogFGo7JVLSrZr8Sv",
#             "interval": "month",
#             "interval_count": 1,
#             "livemode": false,
#             "metadata": {},
#             "meter": null,
#             "nickname": null,
#             "object": "plan",
#             "product": "prod_SE7XS3bTXMDm9D",
#             "tiers_mode": null,
#             "transform_usage": null,
#             "trial_period_days": null,
#             "usage_type": "licensed"
#           },
#           "pretax_credit_amounts": [],
#           "price": {
#             "active": true,
#             "billing_scheme": "per_unit",
#             "created": 1746037445,
#             "currency": "usd",
#             "custom_unit_amount": null,
#             "id": "price_1RJfIfGaogFGo7JVLSrZr8Sv",
#             "livemode": false,
#             "lookup_key": null,
#             "metadata": {},
#             "nickname": null,
#             "object": "price",
#             "product": "prod_SE7XS3bTXMDm9D",
#             "recurring": {
#               "aggregate_usage": null,
#               "interval": "month",
#               "interval_count": 1,
#               "meter": null,
#               "trial_period_days": null,
#               "usage_type": "licensed"
#             },
#             "tax_behavior": "unspecified",
#             "tiers_mode": null,
#             "transform_quantity": null,
#             "type": "recurring",
#             "unit_amount": 200,
#             "unit_amount_decimal": "200"
#           },
#           "pricing": {
#             "price_details": {
#               "price": "price_1RJfIfGaogFGo7JVLSrZr8Sv",
#               "product": "prod_SE7XS3bTXMDm9D"
#             },
#             "type": "price_details",
#             "unit_amount_decimal": "200"
#           },
#           "proration": false,
#           "proration_details": {
#             "credited_items": null
#           },
#           "quantity": 1,
#           "subscription": "sub_1Rt8qxGaogFGo7JVL26b3vCx",
#           "subscription_item": "si_SomPx0uZUrRoOt",
#           "tax_amounts": [],
#           "tax_rates": [],
#           "taxes": [],
#           "type": "subscription",
#           "unit_amount_excluding_tax": "200"
#         }
#       ],
#       "has_more": false,
#       "object": "list",
#       "total_count": 1,
#       "url": "/v1/invoices/in_1Rt8qxGaogFGo7JVLyQONIDN/lines"
#     },
#     "livemode": false,
#     "metadata": {},
#     "next_payment_attempt": null,
#     "number": "BHT1FUFY-0001",
#     "object": "invoice",
#     "on_behalf_of": null,
#     "paid": true,
#     "paid_out_of_band": false,
#     "parent": {
#       "quote_details": null,
#       "subscription_details": {
#         "metadata": {},
#         "subscription": "sub_1Rt8qxGaogFGo7JVL26b3vCx"
#       },
#       "type": "subscription_details"
#     },
#     "payment_intent": {
#       "amount": 200,
#       "amount_capturable": 0,
#       "amount_details": {
#         "tip": {}
#       },
#       "amount_received": 200,
#       "application": null,
#       "application_fee_amount": null,
#       "automatic_payment_methods": null,
#       "canceled_at": null,
#       "cancellation_reason": null,
#       "capture_method": "automatic",
#       "client_secret": "pi_3Rt8qyGaogFGo7JV0bWT6zPm_secret_tKT8UzwUFDHLn1my4J0UAiOOf",
#       "confirmation_method": "automatic",
#       "created": 1754492528,
#       "currency": "usd",
#       "customer": "cus_SoR2DTJQKyDSzl",
#       "description": "Subscription creation",
#       "excluded_payment_method_types": null,
#       "id": "pi_3Rt8qyGaogFGo7JV0bWT6zPm",
#       "invoice": "in_1Rt8qxGaogFGo7JVLyQONIDN",
#       "last_payment_error": null,
#       "latest_charge": "ch_3Rt8qyGaogFGo7JV0R3jb69k",
#       "livemode": false,
#       "metadata": {},
#       "next_action": null,
#       "object": "payment_intent",
#       "on_behalf_of": null,
#       "payment_method": "pm_1Rt8qYGaogFGo7JVxZKhvirE",
#       "payment_method_configuration_details": null,
#       "payment_method_options": {
#         "amazon_pay": {
#           "express_checkout_element_session_id": null
#         },
#         "card": {
#           "installments": null,
#           "mandate_options": null,
#           "network": null,
#           "request_three_d_secure": "automatic"
#         },
#         "cashapp": {},
#         "klarna": {
#           "preferred_locale": null
#         },
#         "link": {
#           "persistent_token": null
#         }
#       },
#       "payment_method_types": [
#         "amazon_pay",
#         "card",
#         "cashapp",
#         "klarna",
#         "link"
#       ],
#       "processing": null,
#       "receipt_email": null,
#       "review": null,
#       "setup_future_usage": null,
#       "shipping": null,
#       "source": null,
#       "statement_descriptor": null,
#       "statement_descriptor_suffix": null,
#       "status": "succeeded",
#       "transfer_data": null,
#       "transfer_group": null
#     },
#     "payment_settings": {
#       "default_mandate": null,
#       "payment_method_options": null,
#       "payment_method_types": null
#     },
#     "period_end": 1754492527,
#     "period_start": 1754492527,
#     "post_payment_credit_notes_amount": 0,
#     "pre_payment_credit_notes_amount": 0,
#     "quote": null,
#     "receipt_number": "2387-9071",
#     "rendering": null,
#     "shipping_cost": null,
#     "shipping_details": null,
#     "starting_balance": 0,
#     "statement_descriptor": null,
#     "status": "paid",
#     "status_transitions": {
#       "finalized_at": 1754492527,
#       "marked_uncollectible_at": null,
#       "paid_at": 1754492527,
#       "voided_at": null
#     },
#     "subscription": "sub_1Rt8qxGaogFGo7JVL26b3vCx",
#     "subscription_details": {
#       "metadata": {}
#     },
#     "subtotal": 200,
#     "subtotal_excluding_tax": 200,
#     "tax": null,
#     "test_clock": null,
#     "total": 200,
#     "total_discount_amounts": [],
#     "total_excluding_tax": 200,
#     "total_pretax_credit_amounts": [],
#     "total_tax_amounts": [],
#     "total_taxes": [],
#     "transfer_data": null,
#     "webhooks_delivered_at": 1754492527
#   },
#   "livemode": false,
#   "metadata": {},
#   "next_pending_invoice_item_invoice": null,
#   "object": "subscription",
#   "on_behalf_of": null,
#   "pause_collection": null,
#   "payment_settings": {
#     "payment_method_options": null,
#     "payment_method_types": null,
#     "save_default_payment_method": "off"
#   },
#   "pending_invoice_item_interval": null,
#   "pending_setup_intent": null,
#   "pending_update": null,
#   "plan": {
#     "active": true,
#     "aggregate_usage": null,
#     "amount": 200,
#     "amount_decimal": "200",
#     "billing_scheme": "per_unit",
#     "created": 1746037445,
#     "currency": "usd",
#     "id": "price_1RJfIfGaogFGo7JVLSrZr8Sv",
#     "interval": "month",
#     "interval_count": 1,
#     "livemode": false,
#     "metadata": {},
#     "meter": null,
#     "nickname": null,
#     "object": "plan",
#     "product": "prod_SE7XS3bTXMDm9D",
#     "tiers_mode": null,
#     "transform_usage": null,
#     "trial_period_days": null,
#     "usage_type": "licensed"
#   },
#   "quantity": 1,
#   "schedule": null,
#   "start_date": 1754492527,
#   "status": "active",
#   "test_clock": null,
#   "transfer_data": null,
#   "trial_end": null,
#   "trial_settings": {
#     "end_behavior": {
#       "missing_payment_method": "create_invoice"
#     }
#   },
#   "trial_start": null
# }

