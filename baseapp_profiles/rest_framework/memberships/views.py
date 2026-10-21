import swapper
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle

from baseapp_core.rest_framework.decorators import action
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as invitation_service
from baseapp_profiles.services import members as member_service

from ..mixins import CurrentProfileMixin
from .filters import ProfileInvitationFilter, ProfileMemberFilter
from .permissions import (
    CanAddProfileMembers,
    CanChangeProfileMembers,
    CanDeleteProfileMembers,
    CanViewProfileMembers,
    HasCurrentProfile,
    get_current_profile,
)
from .serializers import (
    InvitationResponseSerializer,
    InvitationSignupSerializer,
    ProfileInvitationSendSerializer,
    ProfileInvitationSentSerializer,
    ProfileInvitationSerializer,
    ProfileMemberRoleSerializer,
    ProfileMemberSerializer,
    PublicInvitationSerializer,
)
from .throttles import InvitationTokenThrottle

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

TOKEN_URL = r"by-token/(?P<token>[^/]+)"


class ProfileMembershipAPIError(APIException):
    """
    A refused membership operation: `{"non_field_errors": [message], "code": code}`.

    `code` is the same stable reason the GraphQL mutations return in `extensions.code`.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    STATUS_BY_CODE = {
        "invalid_token": status.HTTP_404_NOT_FOUND,
        "signup_disabled": status.HTTP_403_FORBIDDEN,
        "wrong_user": status.HTTP_403_FORBIDDEN,
        "user_exists": status.HTTP_409_CONFLICT,
    }

    def __init__(self, error: ProfileMembershipError) -> None:
        self.status_code = self.STATUS_BY_CODE.get(error.code, status.HTTP_400_BAD_REQUEST)
        super().__init__(detail={"non_field_errors": [error.message], "code": error.code})


class ProfileMembersViewSet(
    CurrentProfileMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Members of the current profile (the `Current-Profile` header).

    Endpoints:
        GET    /profile-members                   List members (active and deactivated)
        GET    /profile-members/{id}              Retrieve a member
        PATCH  /profile-members/{id}              Change the role: {"role": <int>}
        DELETE /profile-members/{id}              Remove the member
        POST   /profile-members/{id}/deactivate   Deactivate (keeps the row, revokes access)
        POST   /profile-members/{id}/reactivate   Reactivate a deactivated member

    Members of the profile may read; changing and removing members takes the
    `change_profileuserrole` / `delete_profileuserrole` permissions on the profile. The last
    active admin cannot be demoted, deactivated or removed (see the README).
    """

    serializer_class = ProfileMemberSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProfileMemberFilter

    def get_queryset(self) -> QuerySet:
        profile = get_current_profile(self.request)
        if profile is None:
            return ProfileUserRole.objects.none()
        return (
            ProfileUserRole.objects.memberships()
            .filter(profile=profile)
            .select_related("user", "profile")
            .order_by("pk")
        )

    def get_permissions(self) -> list[BasePermission]:
        permissions = [IsAuthenticated(), HasCurrentProfile()]
        if self.action in ("list", "retrieve"):
            permissions.append(CanViewProfileMembers())
        elif self.action == "destroy":
            permissions.append(CanDeleteProfileMembers())
        else:
            permissions.append(CanChangeProfileMembers())
        return permissions

    def _respond(self, membership: "ProfileUserRole") -> Response:
        return Response(self.get_serializer(membership).data)

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        membership = self.get_object()
        serializer = ProfileMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            member_service.change_member_role(
                membership, serializer.validated_data["role"], by=request.user
            )
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return self._respond(membership)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        try:
            member_service.remove_member(self.get_object(), by=request.user)
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, *args, **kwargs) -> Response:
        membership = self.get_object()
        try:
            member_service.deactivate_member(membership, by=request.user)
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return self._respond(membership)

    @action(detail=True, methods=["post"])
    def reactivate(self, request: Request, *args, **kwargs) -> Response:
        membership = self.get_object()
        try:
            member_service.reactivate_member(membership, by=request.user)
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return self._respond(membership)


class ProfileInvitationsViewSet(
    CurrentProfileMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Invitations to the current profile (the `Current-Profile` header), and the token
    endpoints an invitee uses.

    Endpoints:
        GET  /profile-invitations                       List invitations (all statuses;
                                                        filter with ?status=, ?role=, ?q=)
        POST /profile-invitations                       Invite in bulk
        GET  /profile-invitations/{id}                  Retrieve an invitation
        POST /profile-invitations/{id}/resend           Send again with a fresh token
        POST /profile-invitations/{id}/cancel           Withdraw a pending invitation
        GET  /profile-invitations/by-token/{token}      Public summary (no sign-in)
        POST /profile-invitations/by-token/{token}/accept               Accept (signed in)
        POST /profile-invitations/by-token/{token}/decline              Decline (signed in)
        POST /profile-invitations/by-token/{token}/accept-with-signup   Accept by choosing a
                                                        password (no sign-in; opt-in setting)

    The public endpoints are rate-limited per IP (`BASEAPP_PROFILES_INVITATION_PUBLIC_RATE`).
    """

    serializer_class = ProfileInvitationSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProfileInvitationFilter

    PUBLIC_ACTIONS = ("lookup", "accept_with_signup")
    INVITEE_ACTIONS = ("accept", "decline")

    def get_queryset(self) -> QuerySet:
        profile = get_current_profile(self.request)
        if profile is None:
            return ProfileUserRole.objects.none()
        return (
            ProfileUserRole.objects.invitations()
            .filter(profile=profile)
            .select_related("profile")
            .order_by("-pk")
        )

    def get_permissions(self) -> list[BasePermission]:
        if self.action in self.PUBLIC_ACTIONS:
            return [AllowAny()]
        if self.action in self.INVITEE_ACTIONS:
            return [IsAuthenticated()]

        permissions = [IsAuthenticated(), HasCurrentProfile()]
        if self.action in ("list", "retrieve"):
            permissions.append(CanViewProfileMembers())
        elif self.action == "cancel":
            permissions.append(CanDeleteProfileMembers())
        else:
            permissions.append(CanAddProfileMembers())
        return permissions

    def get_throttles(self) -> list[BaseThrottle]:
        throttles = super().get_throttles()
        if self.action in self.PUBLIC_ACTIONS:
            throttles.append(InvitationTokenThrottle())
        return throttles

    def _sent_response(
        self, result: invitation_service.SentInvitations, status_code: int
    ) -> Response:
        data = ProfileInvitationSentSerializer(
            {
                "invitations": result.invitations,
                "emails_sent": result.emails_sent,
                "emails_held": len(result.held),
            },
            context=self.get_serializer_context(),
        ).data
        return Response(data, status=status_code)

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = ProfileInvitationSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = invitation_service.send_invitations(
                get_current_profile(request),
                serializer.validated_data["invitees"],
                role=serializer.validated_data["role"],
                invited_by=request.user,
                message=serializer.validated_data["message"],
            )
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return self._sent_response(result, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def resend(self, request: Request, *args, **kwargs) -> Response:
        try:
            result = invitation_service.resend_invitation(self.get_object(), by=request.user)
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return self._sent_response(result, status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, *args, **kwargs) -> Response:
        try:
            invitation = invitation_service.cancel_invitation(self.get_object(), by=request.user)
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        if invitation.pk is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(self.get_serializer(invitation).data)

    @action(detail=False, methods=["get"], url_path=TOKEN_URL, url_name="lookup")
    def lookup(self, request: Request, token: str, *args, **kwargs) -> Response:
        invitation = invitation_service.lookup_invitation(token)
        if invitation is None:
            raise ProfileMembershipAPIError(
                ProfileMembershipError(_("Invalid invitation token"), "invalid_token")
            )
        return Response(PublicInvitationSerializer(invitation).data)

    @action(detail=False, methods=["post"], url_path=f"{TOKEN_URL}/accept", url_name="accept")
    def accept(self, request: Request, token: str, *args, **kwargs) -> Response:
        try:
            invitation = invitation_service.accept_invitation(token, request.user)
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return Response(
            InvitationResponseSerializer(invitation, context=self.get_serializer_context()).data
        )

    @action(detail=False, methods=["post"], url_path=f"{TOKEN_URL}/decline", url_name="decline")
    def decline(self, request: Request, token: str, *args, **kwargs) -> Response:
        try:
            invitation = invitation_service.decline_invitation(token, request.user)
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return Response(
            InvitationResponseSerializer(invitation, context=self.get_serializer_context()).data
        )

    @action(
        detail=False,
        methods=["post"],
        url_path=f"{TOKEN_URL}/accept-with-signup",
        url_name="accept-with-signup",
    )
    def accept_with_signup(self, request: Request, token: str, *args, **kwargs) -> Response:
        serializer = InvitationSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invitation = invitation_service.accept_invitation_with_signup(
                token,
                password=serializer.validated_data["password"],
                first_name=serializer.validated_data.get("first_name"),
                last_name=serializer.validated_data.get("last_name"),
            )
        except ProfileMembershipError as error:
            raise ProfileMembershipAPIError(error)
        return Response(
            InvitationResponseSerializer(invitation, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )
