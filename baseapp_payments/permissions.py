import swapper
from constance import config
from rest_framework.permissions import BasePermission

Customer = swapper.load_model("baseapp_payments", "Customer")
payment_customer_app_label = Customer._meta.app_label


class HasCustomerPermissions(BasePermission):
    def has_permission(self, request, view):
        customer_entity_model = config.STRIPE_CUSTOMER_ENTITY_MODEL
        remote_customer_id = request.query_params.get("remote_customer_id")
        if remote_customer_id:
            customer = Customer.objects.filter(remote_customer_id=remote_customer_id).first()
            if customer:
                if customer_entity_model == "profiles.Profile":
                    return (
                        customer.entity.owner.id == request.user.profile.id
                        or request.user.profile.role == "admin"
                    )
                return customer.entity.id == request.user.id
            return False
        else:
            if customer_entity_model == "profiles.Profile":
                customer = Customer.objects.filter(entity_id=request.user.profile.id).first()
                if customer:
                    return (
                        customer.entity.owner.id == request.user.profile.id
                        or request.user.profile.role == "admin"
                    )
                return False
            else:
                customer = Customer.objects.filter(entity_id=request.user.id).first()
                if customer:
                    return (
                        customer.entity.owner.id == request.user.profile.id
                        or request.user.profile.role == "admin"
                    )
                return False
