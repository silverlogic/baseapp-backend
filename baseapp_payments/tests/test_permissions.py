import pytest

from baseapp_payments.permissions import HasCustomerPermissions

from .factories import CustomerFactory, UserFactory


@pytest.mark.django_db
def test_has_self_customer_permissions_failure():
    user = UserFactory()
    CustomerFactory(entity=user.profile, remote_customer_id="cus_123")
    assert not HasCustomerPermissions().has_permission(user, "view_customer")

@pytest.mark.django_db
def test_has_self_customer_permissions_success():
    user = UserFactory()
    CustomerFactory(entity=user.profile, remote_customer_id="cus_123", authorized_users=[user])
    assert HasCustomerPermissions().has_permission(user, "view_customer")

@pytest.mark.django_db
def test_has_other_entity_customer_permissions_success():
    user = UserFactory()
    other_user = UserFactory()
    CustomerFactory(entity=other_user.profile, remote_customer_id="cus_123", authorized_users=[user])
    assert HasCustomerPermissions().has_permission(user, "view_customer")
