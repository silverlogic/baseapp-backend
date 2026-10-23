"""
The invitation lifecycle: send, hold, resend, cancel, accept (signed in or by signing up),
decline and expire.

These functions check business rules, not permissions: the caller (a mutation, a view, an
admin action, an importer) decides who may act and passes that user along for the audit
trail. They raise `ProfileMembershipError`, whose `code` the API layers pass through.

Two settings change how history is kept (see the README): with
`BASEAPP_PROFILES_INVITATION_KEEP_HISTORY` on, a cancelled invitation is marked CANCELLED
rather than deleted, and inviting an email again adds a new row instead of reusing the
declined, expired or cancelled one.

With `BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER` a project lets an invitation claim an
existing ACTIVE row (a placeholder member whose account was never used). The invitation is
carried on that row without changing its status; see `is_member_claim`.
"""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import swapper
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from baseapp_profiles import signals
from baseapp_profiles.conf import (
    invitation_async_send,
    invitation_can_invite_member,
    invitation_email_sender,
    invitation_expiration_days,
    invitation_max_per_send,
    invitation_pre_send_hook,
    invitation_resend_min_interval,
    invitation_signup_can_reactivate,
    invitation_signup_enabled,
    invitation_validator,
    keep_invitation_history,
)
from baseapp_profiles.exceptions import ProfileMembershipError

from ._utils import send_on_commit
from .members import set_extra_fields, validate_role

logger = logging.getLogger(__name__)

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
Status = ProfileUserRole.ProfileRoleStatus


@dataclass(frozen=True)
class Invitee:
    """Who to invite. Only `email` is required; the names personalise the email."""

    email: str
    first_name: str = ""
    last_name: str = ""


@dataclass
class SentInvitations:
    """The rows a send or resend produced, and how many emails went out (or were queued)."""

    invitations: list = field(default_factory=list)
    emails_sent: int = 0
    # Invitations the pre-send hook held back; send them later with `release_invitation`.
    held: list = field(default_factory=list)


@dataclass(frozen=True)
class PublicInvitation:
    """What anyone holding an invitation token may learn about it — and nothing more."""

    profile_name: str
    invited_email: str
    role: int
    status: int
    expires_at: datetime | None
    invited_first_name: str = ""
    invited_last_name: str = ""
    # Who sent it (full name, else email); empty when nobody did (an import, say).
    inviter_name: str = ""
    message: str = ""
    # The profile's image field file (falsy when it has none).
    profile_image: object = None
    # An active account exists for the invited email, so the invitee signs in to accept
    # (accept-with-signup refuses it with `user_exists`). It may have no usable password,
    # say a social login: the acceptance page offers the project's sign-in either way.
    requires_sign_in: bool = False


# --- Sending -----------------------------------------------------------------------------


def _normalize_invitees(invitees: Iterable[str | Invitee | Mapping]) -> list[Invitee]:
    """Lower-case and de-duplicate the emails, keeping the first mention of each."""
    normalized = []
    seen = set()
    for item in invitees or []:
        if isinstance(item, str):
            item = Invitee(email=item)
        elif isinstance(item, Mapping):
            item = Invitee(
                email=item.get("email") or "",
                first_name=item.get("first_name") or "",
                last_name=item.get("last_name") or "",
            )
        email = (item.email or "").strip().lower()
        if email and email not in seen:
            seen.add(email)
            normalized.append(
                Invitee(
                    email=email,
                    first_name=(item.first_name or "").strip(),
                    last_name=(item.last_name or "").strip(),
                )
            )
    return normalized


def find_user_by_email(email: str) -> AbstractBaseUser | None:
    """The user registered with `email` (case-insensitive), if any."""
    User = get_user_model()
    email_field = User.get_email_field_name()
    return User._default_manager.filter(**{f"{email_field}__iexact": email}).first()


def can_invite_member(membership: "ProfileUserRole") -> bool:
    """
    Whether an invitation may claim the ACTIVE row `membership`, according to
    `BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER` (by default it may not).
    """
    hook = invitation_can_invite_member()
    return hook is not None and bool(hook(membership))


def is_member_claim(invitation: "ProfileUserRole") -> bool:
    """
    Whether `invitation` is an ACTIVE membership carrying an unanswered invitation that
    claims it: it has a token, has not been answered since it was sent, and the project's
    `BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER` still allows it.

    Accepting a claim keeps the row (and its pk) ACTIVE and binds the invitee's account
    to it; cancelling clears the token.
    """
    return (
        invitation.status == Status.ACTIVE
        and bool(invitation.invitation_token)
        and invitation.responded_at is None
        and can_invite_member(invitation)
    )


def awaits_answer(invitation: "ProfileUserRole") -> bool:
    """Whether `invitation` can still be answered: PENDING, or an open member claim."""
    return invitation.status == Status.PENDING or is_member_claim(invitation)


def _renew_token(invitation: "ProfileUserRole") -> None:
    """Give `invitation` a fresh token and expiry date, as unanswered."""
    now = timezone.now()
    invitation.invited_at = now
    invitation.invitation_expires_at = now + timedelta(days=invitation_expiration_days())
    invitation.responded_at = None
    invitation.generate_invitation_token()


def _reset_for_send(invitation: "ProfileUserRole") -> None:
    """Re-open `invitation` as PENDING with a fresh token and expiry date."""
    invitation.status = Status.PENDING
    invitation.deactivated_at = None
    invitation.deactivated_by = None
    _renew_token(invitation)


def _validate_invitee(
    profile: "Profile", invitee: Invitee, invited_by: AbstractBaseUser | None
) -> None:
    """Let `BASEAPP_PROFILES_INVITATION_VALIDATOR` refuse the invitee."""
    validator = invitation_validator()
    if validator is not None:
        validator(profile, invitee, invited_by)


def _open_invitation(
    profile: "Profile",
    invitee: Invitee,
    *,
    role: int,
    invited_user: AbstractBaseUser | None,
    invited_by: AbstractBaseUser | None,
    message: str,
    extra_fields: Mapping | None = None,
) -> "ProfileUserRole":
    """
    Create a PENDING invitation for `invitee` on `profile`, or revive the row that stands
    in its way. Must run inside a transaction: it locks the person's existing rows.

    Raises on a hard conflict: the person is already an active member (unless the project
    lets the invitation claim their row), or holds a pending invitation that has not
    expired. The project's validator may refuse the invitee first.
    """
    _validate_invitee(profile, invitee, invited_by)

    match = Q(invited_email__iexact=invitee.email)
    if invited_user is not None:
        match |= Q(user=invited_user)
    rows = list(
        ProfileUserRole.objects.select_for_update()
        .filter(profile=profile)
        .filter(match)
        # The newest row first: with history on there can be several closed ones.
        .order_by("-pk")
    )
    open_row = next((row for row in rows if row.status in ProfileUserRole.open_statuses()), None)

    reuse = None
    if open_row is not None:
        if open_row.status == Status.ACTIVE:
            if not can_invite_member(open_row):
                raise ProfileMembershipError(
                    _("%(email)s is already a member of this profile") % {"email": invitee.email},
                    "already_member",
                )
            if is_member_claim(open_row) and not open_row.is_invitation_expired():
                raise ProfileMembershipError(
                    _("An invitation has already been sent to %(email)s")
                    % {"email": invitee.email},
                    "duplicate_invitation",
                )
            return _open_member_claim(
                open_row,
                invitee,
                invited_by=invited_by,
                message=message,
                extra_fields=extra_fields,
            )
        if open_row.status == Status.PENDING:
            if not open_row.is_invitation_expired():
                raise ProfileMembershipError(
                    _("An invitation has already been sent to %(email)s")
                    % {"email": invitee.email},
                    "duplicate_invitation",
                )
            expire_invitation(open_row)
        else:
            # A deactivated member: invite them back on the same row.
            reuse = open_row

    if reuse is None and rows and not keep_invitation_history():
        # Without history a person keeps a single row per profile, so a declined, expired
        # or cancelled invitation is re-opened rather than joined by a new one.
        reuse = next(
            (row for row in rows if (row.invited_email or "").lower() == invitee.email),
            rows[0],
        )

    if reuse is not None:
        invitation = reuse
        if invited_user is not None:
            invitation.user = invited_user
        invitation.invited_email = invitee.email
        invitation.invited_first_name = invitee.first_name or invitation.invited_first_name
        invitation.invited_last_name = invitee.last_name or invitation.invited_last_name
        invitation.role = role
        invitation.message = message
        invitation.invited_by = invited_by
    else:
        invitation = ProfileUserRole(
            profile=profile,
            user=invited_user,
            invited_email=invitee.email,
            invited_first_name=invitee.first_name,
            invited_last_name=invitee.last_name,
            role=role,
            message=message,
            invited_by=invited_by,
        )
    set_extra_fields(invitation, extra_fields)
    _reset_for_send(invitation)
    try:
        with transaction.atomic():
            invitation.save()
    except IntegrityError:
        raise ProfileMembershipError(
            _("An invitation has already been sent to %(email)s") % {"email": invitee.email},
            "duplicate_invitation",
        )
    return invitation


def _open_member_claim(
    membership: "ProfileUserRole",
    invitee: Invitee,
    *,
    invited_by: AbstractBaseUser | None,
    message: str,
    extra_fields: Mapping | None,
) -> "ProfileUserRole":
    """
    Carry an invitation on the ACTIVE row `membership`. Its status, role and user stay as
    they are; only the invitation fields are written.
    """
    membership.invited_email = invitee.email
    membership.invited_first_name = invitee.first_name or membership.invited_first_name
    membership.invited_last_name = invitee.last_name or membership.invited_last_name
    membership.message = message
    membership.invited_by = invited_by
    set_extra_fields(membership, extra_fields)
    _renew_token(membership)
    membership.save()
    return membership


def send_invitations(
    profile: "Profile",
    invitees: Iterable[str | Invitee | Mapping],
    *,
    role: int | None = None,
    invited_by: AbstractBaseUser | None = None,
    message: str = "",
    extra_fields: Mapping | None = None,
) -> SentInvitations:
    """
    Invite each of `invitees` (emails, `Invitee`s or dicts with `email`, `first_name`,
    `last_name`) to `profile` with `role` (MANAGER by default).

    `extra_fields` (field name -> value) is set on every row the send opens, for the
    columns a project adds to its concrete `ProfileUserRole`.

    All-or-nothing: a conflict on any email, or an invitee the project's validator refuses,
    rolls back the whole batch. Once the rows are saved, each email goes out unless the
    pre-send hook holds it; a failed email does not undo its invitation.
    """
    if role is None:
        role = ProfileUserRole.ProfileRoles.MANAGER
    validate_role(role)

    items = _normalize_invitees(invitees)
    if not items:
        raise ProfileMembershipError(_("At least one email is required"), "invalid_input")
    limit = invitation_max_per_send()
    if limit is not None and len(items) > limit:
        raise ProfileMembershipError(
            _("At most %(limit)d invitations can be sent at once") % {"limit": limit},
            "invalid_input",
        )

    with transaction.atomic():
        invitations = [
            _open_invitation(
                profile,
                item,
                role=role,
                invited_user=find_user_by_email(item.email),
                invited_by=invited_by,
                message=message or "",
                extra_fields=extra_fields,
            )
            for item in items
        ]

    result = SentInvitations(invitations=invitations)
    for invitation in invitations:
        _deliver_or_hold(invitation, inviter=invited_by, result=result)
    return result


def _ensure_resend_allowed(invitation: "ProfileUserRole") -> None:
    """Refuse a resend sooner than `BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL`."""
    interval = invitation_resend_min_interval()
    last_sent = invitation.last_sent_at or invitation.invited_at
    if interval and last_sent and timezone.now() - last_sent < timedelta(seconds=interval):
        raise ProfileMembershipError(
            _("This invitation was sent moments ago. Try again later."), "resend_too_soon"
        )


def resend_invitation(
    invitation: "ProfileUserRole",
    *,
    by: AbstractBaseUser | None = None,
    extra_fields: Mapping | None = None,
) -> SentInvitations:
    """
    Send a PENDING or EXPIRED invitation (or an open member claim) again with a fresh
    token and expiry date. `extra_fields` is set on the row that is sent.

    With history on, an invitation that has expired stays on record as EXPIRED and the
    resend opens a new row for the same person (returned in `invitations`).
    """
    with transaction.atomic():
        # Lock and re-read: the invitee may have answered since `invitation` was loaded, and
        # saving the stale copy would reopen their answer with a fresh token.
        if ProfileUserRole.objects.select_for_update().filter(pk=invitation.pk).first() is None:
            raise ProfileMembershipError(
                _("Can only resend expired or pending invitations"), "invalid_status"
            )
        invitation.refresh_from_db()
        claim = is_member_claim(invitation)
        if not claim and invitation.status not in [Status.EXPIRED, Status.PENDING]:
            raise ProfileMembershipError(
                _("Can only resend expired or pending invitations"), "invalid_status"
            )
        _ensure_resend_allowed(invitation)

        is_expired = invitation.status == Status.EXPIRED or invitation.is_invitation_expired()
        if claim:
            set_extra_fields(invitation, extra_fields)
            _renew_token(invitation)
            invitation.save()
        elif keep_invitation_history() and is_expired:
            invitee = Invitee(
                email=(invitation.invited_email or "").lower(),
                first_name=invitation.invited_first_name,
                last_name=invitation.invited_last_name,
            )
            invitation = _open_invitation(
                invitation.profile,
                invitee,
                role=invitation.role,
                invited_user=invitation.user or find_user_by_email(invitee.email),
                invited_by=by or invitation.invited_by,
                message=invitation.message,
                extra_fields=extra_fields,
            )
        else:
            set_extra_fields(invitation, extra_fields)
            _reset_for_send(invitation)
            invitation.save()

    result = SentInvitations(invitations=[invitation])
    _deliver_or_hold(invitation, inviter=by, result=result)
    return result


def is_held(invitation: "ProfileUserRole") -> bool:
    """
    Ask `BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK` whether to hold `invitation` back.

    A hook that raises holds the invitation: a broken review gate must not let it through.
    """
    hook = invitation_pre_send_hook()
    if hook is None:
        return False
    try:
        return bool(hook(invitation))
    except Exception:
        logger.exception("Invitation pre-send hook failed; holding invitation %s", invitation.pk)
        return True


def _deliver_or_hold(
    invitation: "ProfileUserRole", *, inviter: AbstractBaseUser | None, result: SentInvitations
) -> None:
    if is_held(invitation):
        # A held invitation does not expire while it waits; `release_invitation` starts
        # the clock when it is finally sent.
        invitation.invitation_expires_at = None
        invitation.save(update_fields=["invitation_expires_at"])
        result.held.append(invitation)
        return
    if deliver_invitation(invitation, inviter=inviter):
        result.emails_sent += 1


def release_invitation(
    invitation: "ProfileUserRole", *, by: AbstractBaseUser | None = None
) -> bool:
    """
    Send an invitation the pre-send hook held back (the hook is not asked again).

    Returns whether the email went out (or was queued).
    """
    if not awaits_answer(invitation):
        raise ProfileMembershipError(_("Can only send pending invitations"), "invalid_status")
    if invitation.invitation_expires_at is None:
        invitation.invitation_expires_at = timezone.now() + timedelta(
            days=invitation_expiration_days()
        )
        invitation.save(update_fields=["invitation_expires_at"])
    return deliver_invitation(invitation, inviter=by or invitation.invited_by)


def _celery_is_eager() -> bool:
    from celery import current_app

    return bool(
        getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False) or current_app.conf.task_always_eager
    )


def deliver_invitation(
    invitation: "ProfileUserRole", *, inviter: AbstractBaseUser | None = None
) -> bool:
    """
    Send the invitation email now, or queue it when `BASEAPP_PROFILES_INVITATION_ASYNC_SEND`
    is on. A queued email leaves once the transaction commits; while Celery runs eagerly it
    is sent inline instead, so the result reflects the real outcome.
    """
    if invitation_async_send() and not _celery_is_eager():
        from baseapp_profiles.tasks import send_invitation_email_task

        invitation_pk = invitation.pk
        inviter_pk = getattr(inviter, "pk", None)
        transaction.on_commit(lambda: send_invitation_email_task.delay(invitation_pk, inviter_pk))
        return True
    return send_invitation_email_now(invitation, inviter=inviter)


def send_invitation_email_now(
    invitation: "ProfileUserRole", *, inviter: AbstractBaseUser | None = None
) -> bool:
    """
    Email the invitation through `BASEAPP_PROFILES_INVITATION_EMAIL_SENDER`, then count it
    and send `invitation_sent`.
    """
    try:
        invitation_email_sender()(invitation, inviter)
    except Exception:
        logger.exception("Failed to send invitation email for invitation %s", invitation.pk)
        return False

    now = timezone.now()
    ProfileUserRole.objects.filter(pk=invitation.pk).update(
        sent_count=F("sent_count") + 1, last_sent_at=now
    )
    invitation.sent_count += 1
    invitation.last_sent_at = now
    send_on_commit(signals.invitation_sent, invitation, inviter=inviter)
    return True


# --- Cancelling and expiring -------------------------------------------------------------


def cancel_invitation(
    invitation: "ProfileUserRole", *, by: AbstractBaseUser | None = None
) -> "ProfileUserRole":
    """
    Withdraw a PENDING invitation. With history on the row is kept as CANCELLED (its token
    then reports the cancellation); otherwise it is deleted.

    Cancelling a member claim clears its token and leaves the membership as it was.
    """
    if not awaits_answer(invitation):
        raise ProfileMembershipError(_("Can only cancel pending invitations"), "invalid_status")

    with transaction.atomic():
        # Lock and re-check: the invitee may have accepted or declined since `invitation`
        # was loaded, and that answer must not be overwritten or deleted.
        current = ProfileUserRole.objects.select_for_update().filter(pk=invitation.pk).first()
        if current is None or not awaits_answer(current):
            raise ProfileMembershipError(_("Can only cancel pending invitations"), "invalid_status")
        if current.status == Status.ACTIVE:
            invitation.invitation_token = None
            invitation.save(update_fields=["invitation_token"])
        elif keep_invitation_history():
            invitation.status = Status.CANCELLED
            invitation.deactivated_at = timezone.now()
            invitation.deactivated_by = by
            invitation.save(update_fields=["status", "deactivated_at", "deactivated_by"])
        else:
            invitation.delete()
        send_on_commit(signals.invitation_cancelled, invitation, by=by)
    return invitation


def expire_invitation(invitation: "ProfileUserRole") -> None:
    """Mark a PENDING invitation EXPIRED and send `invitation_expired`."""
    invitation.status = Status.EXPIRED
    invitation.save(update_fields=["status"])
    send_on_commit(signals.invitation_expired, invitation)


def expire_invitations(now: datetime | None = None) -> int:
    """
    Mark every PENDING invitation past its expiry date EXPIRED; returns how many.

    Rows locked by a concurrent response or cancel are skipped; if still PENDING once that
    commits, the next sweep picks them up.
    """
    with transaction.atomic():
        overdue = list(ProfileUserRole.objects.overdue(now).select_for_update(skip_locked=True))
        for invitation in overdue:
            expire_invitation(invitation)
    return len(overdue)


# --- Responding --------------------------------------------------------------------------


def get_invitation_by_token(token: str) -> "ProfileUserRole":
    invitation = (
        ProfileUserRole.objects.select_related("profile", "invited_by")
        .filter(invitation_token=token)
        .first()
        if token
        else None
    )
    if invitation is None:
        raise ProfileMembershipError(_("Invalid invitation token"), "invalid_token")
    return invitation


def lookup_invitation(token: str) -> PublicInvitation | None:
    """
    The public view of an invitation: enough for an acceptance page to greet the invitee.

    An overdue PENDING invitation is reported as EXPIRED without being written. An open
    member claim reads PENDING (or EXPIRED), though the row itself stays ACTIVE.
    """
    try:
        invitation = get_invitation_by_token(token)
    except ProfileMembershipError:
        return None
    status = Status.PENDING if is_member_claim(invitation) else invitation.status
    if status == Status.PENDING and invitation.is_invitation_expired():
        status = Status.EXPIRED
    invited_email = invitation.invited_email or ""
    account = invitation.user or (find_user_by_email(invited_email) if invited_email else None)
    return PublicInvitation(
        profile_name=invitation.profile.name or "",
        invited_email=invited_email,
        role=invitation.role,
        status=status,
        expires_at=invitation.invitation_expires_at,
        invited_first_name=invitation.invited_first_name,
        invited_last_name=invitation.invited_last_name,
        inviter_name=_display_name(invitation.invited_by),
        message=invitation.message,
        profile_image=invitation.profile.image or None,
        # The inverse of accept_invitation_with_signup's rule, so the page never offers a
        # sign-up that would be refused.
        requires_sign_in=bool(account is not None and account.is_active),
    )


def _display_name(user: AbstractBaseUser | None) -> str:
    if user is None:
        return ""
    full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
    return full_name or getattr(user, user.get_email_field_name(), "") or ""


def _ensure_respondable(invitation: "ProfileUserRole") -> None:
    if is_member_claim(invitation):
        # The row is a membership, so an overdue claim is refused without being written.
        if invitation.is_invitation_expired():
            raise ProfileMembershipError(_("This invitation has expired"), "expired_invitation")
        return
    if invitation.status == Status.PENDING and invitation.is_invitation_expired():
        expire_invitation(invitation)
    if invitation.status == Status.EXPIRED:
        raise ProfileMembershipError(_("This invitation has expired"), "expired_invitation")
    if invitation.status == Status.CANCELLED:
        raise ProfileMembershipError(
            _("This invitation has been cancelled"), "cancelled_invitation"
        )
    if invitation.status != Status.PENDING:
        raise ProfileMembershipError(
            _("This invitation has already been responded to"), "already_responded"
        )


def _bind_user(invitation: "ProfileUserRole", user: AbstractBaseUser) -> None:
    """Attach `user` to the invitation, refusing anyone it was not sent to."""
    if invitation.user_id is None:
        user_email = (getattr(user, user.get_email_field_name(), "") or "").casefold()
        if user_email != (invitation.invited_email or "").casefold():
            raise ProfileMembershipError(
                _("This invitation was sent to a different user"), "wrong_user"
            )
        invitation.user = user
    elif invitation.user_id != user.pk:
        raise ProfileMembershipError(
            _("This invitation was sent to a different user"), "wrong_user"
        )


def _activate(invitation: "ProfileUserRole", user: AbstractBaseUser) -> None:
    if invitation.profile.is_owned_by(user):
        raise ProfileMembershipError(
            _("The profile owner cannot accept an invitation to their own profile"),
            "cannot_add_owner",
        )
    if (
        ProfileUserRole.objects.open()
        .filter(profile_id=invitation.profile_id, user=user)
        .exclude(pk=invitation.pk)
        .exists()
    ):
        raise ProfileMembershipError(
            _("You are already a member of this profile"), "already_member"
        )
    invitation.user = user
    invitation.status = Status.ACTIVE
    invitation.responded_at = timezone.now()
    invitation.save()


def _lock_for_response(invitation: "ProfileUserRole") -> "ProfileUserRole":
    """
    Lock the invitation's row and check again that it can still be answered. Must run inside
    a transaction: a cancel, an expiry sweep or a second submission that got there first
    wins, instead of being overwritten by this response.
    """
    locked = (
        ProfileUserRole.objects.select_for_update(of=("self",))
        .select_related("profile")
        .filter(pk=invitation.pk)
        .first()
    )
    if locked is None:
        # Cancelled (and deleted, with history off) in the meantime.
        raise ProfileMembershipError(_("Invalid invitation token"), "invalid_token")
    _ensure_respondable(locked)
    return locked


def accept_invitation(token: str, user: AbstractBaseUser) -> "ProfileUserRole":
    """Accept the invitation for a signed-in `user`, who must be the one it was sent to."""
    invitation = get_invitation_by_token(token)
    # Checked before locking too, so an overdue invitation is recorded as EXPIRED.
    _ensure_respondable(invitation)
    _bind_user(invitation, user)
    with transaction.atomic():
        invitation = _lock_for_response(invitation)
        _bind_user(invitation, user)
        _activate(invitation, user)
        send_on_commit(signals.invitation_accepted, invitation, user=user, created_user=False)
    return invitation


def decline_invitation(token: str, user: AbstractBaseUser) -> "ProfileUserRole":
    """Decline the invitation for a signed-in `user`, who must be the one it was sent to."""
    invitation = get_invitation_by_token(token)
    _ensure_respondable(invitation)
    _bind_user(invitation, user)
    with transaction.atomic():
        invitation = _lock_for_response(invitation)
        _bind_user(invitation, user)
        if invitation.status != Status.ACTIVE:
            # Declining a member claim leaves the membership as it was.
            invitation.status = Status.DECLINED
        invitation.responded_at = timezone.now()
        invitation.save()
        send_on_commit(signals.invitation_declined, invitation, user=user)
    return invitation


def can_reactivate_on_signup(user: AbstractBaseUser, invitation: "ProfileUserRole") -> bool:
    """
    Whether accept-with-signup may reactivate the inactive account `user`.

    Holding the token only proves control of the inbox, so it must not undo a ban: staff
    and superusers are never reactivated, and by default neither is any account that has
    ever signed in — only accounts created ahead of time (by an import, say) that were never
    used. `BASEAPP_PROFILES_INVITATION_SIGNUP_CAN_REACTIVATE` replaces the second rule.
    """
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return False
    hook = invitation_signup_can_reactivate()
    if hook is not None:
        return bool(hook(user, invitation))
    return getattr(user, "last_login", None) is None


def accept_invitation_with_signup(
    token: str,
    *,
    password: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> "ProfileUserRole":
    """
    Accept an invitation anonymously by choosing a password.

    Creates the account for the invited email — or activates an existing inactive one that
    `can_reactivate_on_signup` allows — sets the password (checked against
    `AUTH_PASSWORD_VALIDATORS`) and the given names, and accepts. Receiving the token proves
    the invitee owns the address, so a user model with an `is_email_verified` field gets it
    set. An email that already has an active account
    must sign in and use `accept_invitation` instead.

    Disabled unless `BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED` is on.
    """
    if not invitation_signup_enabled():
        raise ProfileMembershipError(
            _("Signing up from an invitation is not enabled"), "signup_disabled"
        )

    invitation = get_invitation_by_token(token)
    _ensure_respondable(invitation)
    email = (invitation.invited_email or "").strip().lower()
    if not email:
        raise ProfileMembershipError(
            _("This invitation was not sent to an email address"), "invalid_invitation"
        )

    User = get_user_model()
    with transaction.atomic():
        # Lock the row and re-check, so two submissions of the form cannot both sign up.
        invitation = _lock_for_response(invitation)

        user = invitation.user or find_user_by_email(email)
        if user is not None and user.is_active:
            raise ProfileMembershipError(
                _("An account already exists for this email. Sign in to accept the invitation."),
                "user_exists",
            )
        if user is not None and not can_reactivate_on_signup(user, invitation):
            raise ProfileMembershipError(
                _("This account has been deactivated. Contact an administrator."),
                "account_inactive",
            )

        created_user = user is None
        if created_user:
            user = User(**{User.get_email_field_name(): email})
            if User.USERNAME_FIELD != User.get_email_field_name():
                setattr(user, User.USERNAME_FIELD, email)

        if first_name is not None and hasattr(user, "first_name"):
            user.first_name = first_name.strip()
        if last_name is not None and hasattr(user, "last_name"):
            user.last_name = last_name.strip()

        try:
            validate_password(password, user=user)
        except DjangoValidationError as error:
            raise ProfileMembershipError(" ".join(error.messages), "invalid_password")

        user.set_password(password)
        user.is_active = True
        if hasattr(user, "is_email_verified"):
            user.is_email_verified = True
        user.save()

        _activate(invitation, user)
        send_on_commit(
            signals.invitation_accepted, invitation, user=user, created_user=created_user
        )
    return invitation
