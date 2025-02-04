# BaseApp Payments - Django

This app provides the integration of Stripe with The SilverLogic's [BaseApp](https://bitbucket.org/silverlogic/baseapp-django-v2): [django-restframework](https://www.django-rest-framework.org/) and [dj-stripe](https://dj-stripe.readthedocs.io/en/master/)

## Install the package

Add to `requirements/base.txt`:

```bash
baseapp-payments==0.16.1
```

## Setup Stripe's credentials

Add to your `settings/base.py`:

```py
# Stripe
STRIPE_LIVE_SECRET_KEY = env("STRIPE_LIVE_SECRET_KEY")
STRIPE_TEST_SECRET_KEY = env("STRIPE_TEST_SECRET_KEY")
STRIPE_LIVE_MODE = env("STRIPE_LIVE_MODE")  # Change to True in production
DJSTRIPE_WEBHOOK_SECRET = env("DJSTRIPE_WEBHOOK_SECRET")
DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"
```

## Add the payments_router to your urlpatterns

```py
from baseapp_payments.router import payments_router

v1_urlpatterns = [
    ...
    re_path(r"payments", include(payments_router.urls)),
    ...
]
```

## Subscriber

A subscriber can be an User, an Organization, a Project, any model that have an `email` property. You can specify the model of your subscriber with the setting:

```py
DJSTRIPE_SUBSCRIBER_MODEL='apps.organizations.Organization`
```

Make sure to also implement `get_subscriber_from_request` in your `apps.users.User` to grab the subscriber for the current authenticated user:

```py
class User(PermissionsMixin, AbstractBaseUser):
    ...

    def get_subscriber_from_request(self, request):
        org_pk = request.GET.get('organization')
        return Organization.objects.get(pk=org_pk, admins=request.user)
```

Implement the following methods in the subscriber's model:

```py
class Organization(models.Model):
    def get_subscription_plan(self):
        return self.subscription_plan

    def subscription_start_request(self, plan, customer, subscription, request):
        self.subscription_plan = plan
        self.show_payment_method_action_banner = False
        self.save()

    def subscription_cancel_request(self, customer, subscription, request):
        # in this use case the self.subscription_plan will be set to null when we receive the event from stripe instead
        pass

    def subscription_update_request(self, plan, is_upgrade, request):
        # is_upgrade = current plan's price < new plan's price

        # if we want to upgrade right way but wait to the end of the period to change plans when it is a downgrade:
        if is_upgrade:
            self.subscription_plan = plan
            self.save()

    def subscription_plan_changed_webhook(self, plan, price, event):
        # stripe's event: invoice.paid
        # this method is called if the plan is different from the one returned by self.get_subscription_plan()
        self.subscription_plan = plan
        self.save()

    def subscription_deleted_webhook(self, event):
        # stripe's event: customer.subscription.deleted
        self.subscription_plan = None
        self.show_payment_method_action_banner = True
        self.save()

    def invoice_payment_failed_webhook(self, event):
        # stripe's event: invoice.payment_failed
        self.show_payment_method_action_banner = True
        self.save()
```

## Plan model

You can extend the plan model by inheriting `baseapp_payments.models.BasePlan`:

```py
from django.db import models
from baseapp_payments.models import BasePlan

class SubscriptionPlan(BasePlan):
    video_calls_per_month = models.PositiveIntegerField(default=5)
```

Add to your `settings/base.py` the path to your custom plan model:

```
BASEAPP_PAYMENTS_PLAN_MODEL = "apps.plans.SubscriptionPlan"
```

To **extend the serializer** you can create a normal serializer:

```py

from baseapp_payments.serializers import PlanSerializer
from .models import SubscriptionPlan

class SubscriptionPlanSerializer(PlanSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = super().Meta.fields + (
            "searches_per_month",
            "can_create_favorites",
        )

```

Then add to your `settings/base.py` the path to your custom serializer:

```py
BASEAPP_PAYMENTS_PLAN_SERIALIZER = "apps.plans.serializers.SubscriptionPlanSerializer"
```

## One time payment / buy a product


Implement method stripe_payment_intent_params in your product model:

```py
    def stripe_payment_intent_params(self, request, validated_data):
        price = self.price

        if self.class_type.slug == "donation":
            price = validated_data["amount"]

        amount = int(price * 100)

        return {

            "amount": amount,
            "application_fee_amount": int(self.instructor.stripe_percentage_fee / 100.00 * amount),
            "transfer_data": {"destination": self.instructor.stripe_account_id,},

        }
```

And then call create_payment_intent in the Viewset you're using for 'checkout/purchase' your product:
    [FLOW Example](https://bitbucket.org/silverlogic/flow-backend-django/src/64dbb17acfd05333fb6177c6b2e42c2332d89571/apps/api/v1/classes/views.py?at=master#views.py-178)
```py
    from baseapp_payments.utils import create_payment_intent, stripe


    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[permissions.IsAuthenticated],
        serializer_class=PurchaseClassSerializer,
    )
    def purchase(self, request, *args, **kwargs):
        class_obj = self.get_object()
        user = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.class_obj = class_obj
        serializer.is_valid(raise_exception=True)

        if class_obj.class_type.slug != "free":
            payment_intent = create_payment_intent(class_obj, request, serializer.validated_data)
            ClassStudent.objects.create(student=user, clss=class_obj, payment_intent=payment_intent)
        else:
            ClassStudent.objects.create(student=user, clss=class_obj)

        serializer.send_email()
        return response.Response({}, status=status.HTTP_200_OK)
   
# Stripe's webhook events

You can [listen to any stripe events using the webhooks](https://dj-stripe.readthedocs.io/en/master/usage/webhooks/) 

```py
from djstripe import webhooks

@webhooks.handler("customer.subscription.trial_will_end")
def my_handler(event, **kwargs):
    event.customer.subscriber.show_trial_ended_action_banner = True
    event.customer.subscriber.save()
```

# Two-way sync with Stripe

When the webhook is fully setup all data changed in stripe will be updated in the system receiving the webhooks events. If you have data on Stripe already you can [manually sync](https://dj-stripe.readthedocs.io/en/master/usage/manually_syncing_with_stripe/). For example with the following command you can sync all data:

```bash
./manage.py djstripe_sync_models
```


# To do

 - [ ] Create a special error message to be handled by the frontend package
   Ex: if by trying to perform an action I'm not able due to payment failure or plan is out of credits for that action then show call to action to upgrade
 - [ ] Move tests from FinJoy to this repository
 - [ ] One time payments (to buy a product)
