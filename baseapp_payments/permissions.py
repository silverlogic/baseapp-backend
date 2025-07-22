import swapper
from constance import config
from django.contrib.auth.backends import BaseBackend
from rest_framework.permissions import BasePermission

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")
payments_app_label = Customer._meta.app_label


class PaymentsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm in [
            f"{payments_app_label}.view_customer",
            f"{payments_app_label}.change_customer",
            f"{payments_app_label}.delete_customer",
            f"{payments_app_label}.list_invoices",
            f"{payments_app_label}.list_payment_methods",
            f"{payments_app_label}.add_payment_method",
            f"{payments_app_label}.change_payment_method",
            f"{payments_app_label}.delete_payment_method",
        ]:
            if not obj:
                return False
            if not isinstance(obj, Customer):
                return False
            if config.STRIPE_CUSTOMER_ENTITY_MODEL == "profiles.Profile":
                return obj.entity.id == user_obj.profile.id or obj.entity.members.filter(
                    id=user_obj.id, role=1
                )
            return obj.entity.id == user_obj.id
        if perm in [
            f"{payments_app_label}.add_subscription",
            f"{payments_app_label}.list_subscription",
        ]:
            if not obj:
                return False
            entity_id = obj.get("entity_id")
            if not entity_id:
                return False
            customer = Customer.objects.filter(entity_id=entity_id).first()
            if not customer:
                return False
            if config.STRIPE_CUSTOMER_ENTITY_MODEL == "profiles.Profile":
                return (
                    customer.entity.id == user_obj.profile.id
                    or customer.entity.members.filter(id=user_obj.id, role=1).exists()
                )
            return customer.entity.id == user_obj.id
        if perm in [
            f"{payments_app_label}.view_subscription",
            f"{payments_app_label}.change_subscription",
            f"{payments_app_label}.delete_subscription",
        ]:
            if not obj:
                return False
            if obj and isinstance(obj, Subscription):
                return (
                    obj.customer.entity.id == user_obj.profile.id
                    or obj.customer.entity.members.filter(id=user_obj.id, role=1).exists()
                )
            return False
        return False


class DRFCustomerPermissions(BasePermission):
    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)
        if action == "create":
            return request.user.has_perm("baseapp_payments.add_customer", obj)
        elif action == "retrieve":
            return request.user.has_perm("baseapp_payments.view_customer", obj)
        elif action in ["update", "partial_update"]:
            return request.user.has_perm("baseapp_payments.change_customer", obj)
        elif action == "destroy":
            return request.user.has_perm("baseapp_payments.delete_customer", obj)
        elif action == "invoices":
            return request.user.has_perm("baseapp_payments.list_invoices", obj)
        elif action == "payment_methods":
            return request.user.has_perm("baseapp_payments.list_payment_methods", obj)
        elif action == "create_payment_method":
            return request.user.has_perm("baseapp_payments.add_payment_method", obj)
        elif action == "update_payment_method":
            return request.user.has_perm("baseapp_payments.change_payment_method", obj)
        elif action == "delete_payment_method":
            return request.user.has_perm("baseapp_payments.delete_payment_method", obj)
        return True


class DRFSubscriptionPermissions(BasePermission):
    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)
        if action == "create":
            return request.user.has_perm("baseapp_payments.add_subscription", request.data)
        elif action == "retrieve":
            return request.user.has_perm("baseapp_payments.view_subscription", obj)
        elif action == "list":
            return request.user.has_perm("baseapp_payments.list_subscription", request.data)
        elif action in ["update", "partial_update"]:
            return request.user.has_perm("baseapp_payments.change_subscription", obj)
        elif action == "destroy":
            return request.user.has_perm("baseapp_payments.delete_subscription", obj)
        return True
