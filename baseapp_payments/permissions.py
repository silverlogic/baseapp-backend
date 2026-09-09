import swapper
from constance import config
from django.contrib.auth.backends import BaseBackend
from rest_framework.permissions import BasePermission

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")
# Both models are swappable, so the permissions Django generates for them live under
# whichever app declares the concrete model - not necessarily `baseapp_payments`.
# Building the labels from the models keeps the backend and the DRF classes below in
# agreement about the name whichever app that turns out to be.
payments_app_label = Customer._meta.app_label


def payments_perm(codename: str) -> str:
    return f"{payments_app_label}.{codename}"


# The nested `payment_methods` action multiplexes every verb onto one route, so the
# permission has to be chosen by HTTP method rather than by a distinct DRF action.
PAYMENT_METHOD_PERMS_BY_METHOD = {
    "GET": "list_payment_methods",
    "POST": "add_payment_method",
    "PUT": "change_payment_method",
    "PATCH": "change_payment_method",
    "DELETE": "delete_payment_method",
}

CUSTOMER_PERMS = [
    "view_customer",
    "change_customer",
    "delete_customer",
    "list_invoices",
    "list_payment_methods",
    "add_payment_method",
    "change_payment_method",
    "delete_payment_method",
    "list_subscriptions",
    "add_subscription",
]

SUBSCRIPTION_PERMS = [
    "view_subscription",
    "change_subscription",
    "delete_subscription",
]


def is_entity_owner(entity, user_obj) -> bool:
    """Whether `user_obj` owns, or actively administers, `entity`."""
    if entity is None or not getattr(user_obj, "is_authenticated", False):
        return False
    if config.STRIPE_CUSTOMER_ENTITY_MODEL != "profiles.Profile":
        return entity.id == user_obj.id

    profile = getattr(user_obj, "profile", None)
    if profile is not None and entity.id == profile.id:
        return True

    ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
    # `members` are ProfileUserRole rows, so this filters on the row's user - not on
    # the row's own pk - and only counts memberships that are still active.
    return entity.members.filter(
        user_id=user_obj.id,
        role=ProfileUserRole.ProfileRoles.ADMIN,
        status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
    ).exists()


def _customer_owner(customer, user_obj) -> bool:
    return customer is not None and is_entity_owner(customer.entity, user_obj)


class PaymentsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm in [payments_perm(codename) for codename in CUSTOMER_PERMS]:
            if not isinstance(obj, Customer):
                return False
            return _customer_owner(obj, user_obj)
        if perm in [payments_perm(codename) for codename in SUBSCRIPTION_PERMS]:
            if not isinstance(obj, Subscription):
                return False
            return _customer_owner(obj.customer, user_obj)
        return False


class DRFCustomerPermissions(BasePermission):
    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)
        if action == "retrieve":
            return request.user.has_perm(payments_perm("view_customer"), obj)
        elif action in ["update", "partial_update"]:
            return request.user.has_perm(payments_perm("change_customer"), obj)
        elif action == "destroy":
            return request.user.has_perm(payments_perm("delete_customer"), obj)
        elif action == "invoices":
            return request.user.has_perm(payments_perm("list_invoices"), obj)
        elif action == "payment_methods":
            return request.user.has_perm(
                payments_perm(PAYMENT_METHOD_PERMS_BY_METHOD.get(request.method, "")), obj
            )
        return False


class DRFSubscriptionPermissions(BasePermission):
    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)
        # `create` and `list` have no subscription yet, so `obj` here is the Customer,
        # not a Subscription. Neither route reaches this class on its own - DRF only
        # runs object permissions from get_object() - so both override their handler
        # to call check_object_permissions(request, customer) explicitly. Drop that
        # call and the branches below go dead silently.
        if action == "create":
            return request.user.has_perm(payments_perm("add_subscription"), obj)
        elif action == "list":
            return request.user.has_perm(payments_perm("list_subscriptions"), obj)
        elif action == "retrieve":
            return request.user.has_perm(payments_perm("view_subscription"), obj)
        elif action in ["update", "partial_update"]:
            return request.user.has_perm(payments_perm("change_subscription"), obj)
        elif action == "destroy":
            return request.user.has_perm(payments_perm("delete_subscription"), obj)
        return False
