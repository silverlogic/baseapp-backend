import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.utils.module_loading import import_string
from rest_framework.permissions import BasePermission

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")
# Both models are swappable, so the permissions Django generates for them live under
# whichever app declares the concrete model - not necessarily `baseapp_payments`.
# Building the labels from the models keeps the backend and the DRF classes below in
# agreement about the name whichever app that turns out to be.
payments_app_label = Customer._meta.app_label


def payments_perm(codename: str) -> str:
    # Under the plugin architecture the concrete Customer lives in the consuming
    # project, so the app label is no longer "baseapp_payments". Hardcoding it here
    # silently denied every request.
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


DEFAULT_ENTITY_OWNER_CHECK = "baseapp_payments.permissions.default_entity_owner_check"


def profile_entity_owner(entity, user_obj) -> bool:
    # Imported here rather than at module scope so `baseapp_profiles` stays optional:
    # this function is only reached once the entity is known to be a Profile.
    from baseapp_profiles.permissions import is_active_member

    ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
    own_profile_id = getattr(user_obj, "profile_id", None)
    return (
        entity.owner_id == user_obj.id
        # A user's own profile is billable by them even where `owner` was left unset,
        # which `profile_owner_sql = None` allows. The None check is belt-and-braces:
        # `entity` reaches here from a saved `customer.entity`, but a bare `==` between
        # two absent ids would read as ownership if that ever stopped being true.
        or (own_profile_id is not None and own_profile_id == entity.id)
        or is_active_member(entity, user_obj, role=ProfileUserRole.ProfileRoles.ADMIN)
    )


def default_entity_owner_check(entity, user_obj) -> bool:
    if apps.is_installed("baseapp_profiles"):
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        if isinstance(entity, Profile):
            return profile_entity_owner(entity, user_obj)

    if isinstance(entity, get_user_model()):
        return entity.pk == user_obj.pk

    # Nothing here can know who owns an arbitrary entity model, and guessing is how this
    # went wrong before: comparing the entity's pk to the user's made organization 5 look
    # owned by user 5. A project pointing STRIPE_CUSTOMER_ENTITY_MODEL at its own model
    # has to supply BASEAPP_PAYMENTS_ENTITY_OWNER_CHECK.
    return False


def is_entity_owner(entity, user_obj) -> bool:
    """Whether `user_obj` owns, or actively administers, `entity`."""
    if entity is None or not getattr(user_obj, "is_authenticated", False):
        return False

    path = getattr(settings, "BASEAPP_PAYMENTS_ENTITY_OWNER_CHECK", DEFAULT_ENTITY_OWNER_CHECK)
    return import_string(path)(entity, user_obj)


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
