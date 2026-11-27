"""
Locking checked with two real transactions on two connections, which the other tests
(one transaction each) cannot do.
"""

import threading
from collections.abc import Callable

import pytest
import swapper
from django.db import connection, transaction

from baseapp_core.tests.factories import UserFactory
from baseapp_organizations.services import OrganizationAccountService, OrganizationService
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as invitation_service
from baseapp_profiles.services import members as member_service

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db(transaction=True)

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
HOLD_SECONDS = 1.0


def run_overlapping(first: Callable[[threading.Event], object], second: Callable[[], object]):
    """
    Run `first` and `second` in their own threads (so on their own connections). `first`
    is handed an event to set once it holds its locks; `second` starts only then. Returns
    what each returned, or the exception it raised.
    """
    holding = threading.Event()
    outcomes = {}

    def call(name: str, function: Callable[[], object]) -> None:
        try:
            outcomes[name] = function()
        except Exception as error:  # noqa: BLE001 - the test inspects what was raised
            outcomes[name] = error
        finally:
            connection.close()

    def run_second() -> object:
        assert holding.wait(timeout=10)
        return second()

    threads = [
        threading.Thread(target=call, args=("first", lambda: first(holding))),
        threading.Thread(target=call, args=("second", run_second)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return outcomes["first"], outcomes["second"]


def delete_account(user, holding: threading.Event | None = None) -> str | None:
    """What `delete_account` does: check, then deactivate, in one transaction."""
    with transaction.atomic():
        reason = OrganizationAccountService().get_account_deletion_block_reason(user)
        if holding is not None:
            holding.set()
            threading.Event().wait(HOLD_SECONDS)
        if reason is None:
            user.is_active = False
            user.save(update_fields=["is_active"])
    return None if reason is None else str(reason)


def test_two_admins_deleting_their_accounts_at_once_leave_one_admin() -> None:
    organization = OrganizationService.create("Acme")
    one = ProfileUserRoleFactory(profile=organization.profile, role=ADMIN)
    two = ProfileUserRoleFactory(profile=organization.profile, role=ADMIN)

    first, second = run_overlapping(
        lambda holding: delete_account(one.user, holding), lambda: delete_account(two.user)
    )

    assert first is None
    assert "only admin" in second
    one.user.refresh_from_db()
    two.user.refresh_from_db()
    assert (one.user.is_active, two.user.is_active) == (False, True)


def test_a_promotion_during_an_account_deletion_cannot_strand_the_organization() -> None:
    organization = OrganizationService.create("Acme")
    admin = ProfileUserRoleFactory(profile=organization.profile, role=ADMIN)
    leaving = ProfileUserRoleFactory(profile=organization.profile, role=MANAGER)

    def promote_then_step_down() -> None:
        member_service.change_member_role(leaving, ADMIN)
        member_service.change_member_role(admin, MANAGER)

    first, second = run_overlapping(
        lambda holding: delete_account(leaving.user, holding), promote_then_step_down
    )

    # The deletion went ahead (a manager is free to go); the admin who then tried to hand
    # over to the deleted account is refused, so the organization keeps an admin.
    assert first is None
    assert isinstance(second, ProfileMembershipError)
    assert second.code == "last_admin"
    admin.refresh_from_db()
    assert admin.role == ADMIN


def test_overlapping_invitation_batches_do_not_deadlock() -> None:
    profile = ProfileFactory(owner=UserFactory())
    emails = ["ann@example.com", "bob@example.com"]

    def send_and_hold(holding: threading.Event) -> int:
        with transaction.atomic():
            result = invitation_service.send_invitations(profile, emails)
            holding.set()
            threading.Event().wait(HOLD_SECONDS)
        return len(result.invitations)

    first, second = run_overlapping(
        send_and_hold,
        lambda: invitation_service.send_invitations(profile, list(reversed(emails))),
    )

    # The second batch waited for the first and was then refused cleanly, rather than one
    # of the two being aborted by the database.
    assert first == 2
    assert isinstance(second, ProfileMembershipError)
    assert second.code == "duplicate_invitation"
    assert ProfileUserRole.objects.filter(profile=profile).count() == 2
