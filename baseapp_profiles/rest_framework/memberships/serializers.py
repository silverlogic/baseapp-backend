import swapper
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services.members import validate_role

from ..serializers import JWTProfileSerializer

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


def _validate_assignable_role(role: int) -> int:
    try:
        validate_role(role)
    except ProfileMembershipError as error:
        raise serializers.ValidationError([error.message])
    return role


class ProfileMemberUserSerializer(serializers.Serializer):
    """The member's account: id, email, display name and (when users have one) profile."""

    id = serializers.IntegerField(source="pk")
    email = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()

    def get_email(self, user) -> str:
        return getattr(user, user.get_email_field_name(), "") or ""

    def get_full_name(self, user) -> str:
        return user.get_full_name() if hasattr(user, "get_full_name") else ""

    def get_profile(self, user) -> dict | None:
        profile = getattr(user, "profile", None)
        if profile is None:
            return None
        return JWTProfileSerializer(profile, context=self.context).data


class ProfileMemberSerializer(serializers.ModelSerializer):
    user = ProfileMemberUserSerializer(read_only=True)

    class Meta:
        model = ProfileUserRole
        fields = ("id", "user", "role", "status", "deactivated_at", "deactivated_by")
        read_only_fields = fields


class ProfileMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ProfileUserRole.ProfileRoles.choices)

    def validate_role(self, value: int) -> int:
        return _validate_assignable_role(value)


class ProfileInvitationSerializer(serializers.ModelSerializer):
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = ProfileUserRole
        fields = (
            "id",
            "invited_email",
            "invited_first_name",
            "invited_last_name",
            "role",
            "status",
            "is_expired",
            "message",
            "invited_by",
            "invited_at",
            "invitation_expires_at",
            "responded_at",
            "sent_count",
            "last_sent_at",
            "user",
            "deactivated_at",
            "deactivated_by",
        )
        read_only_fields = fields

    def get_is_expired(self, invitation) -> bool:
        return invitation.status == ProfileUserRole.ProfileRoleStatus.EXPIRED or (
            invitation.status == ProfileUserRole.ProfileRoleStatus.PENDING
            and invitation.is_invitation_expired()
        )


class InviteeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)


class ProfileInvitationSendSerializer(serializers.Serializer):
    """Invite several people at once, with one role and message for all of them."""

    invitations = InviteeSerializer(many=True, required=False)
    emails = serializers.ListField(child=serializers.EmailField(), required=False)
    role = serializers.ChoiceField(
        choices=ProfileUserRole.ProfileRoles.choices,
        default=ProfileUserRole.ProfileRoles.MANAGER,
    )
    message = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_role(self, value: int) -> int:
        return _validate_assignable_role(value)

    def validate(self, attrs: dict) -> dict:
        invitees = [*attrs.get("emails", []), *attrs.get("invitations", [])]
        if not invitees:
            raise serializers.ValidationError(
                {"non_field_errors": [_("At least one email is required")]}
            )
        attrs["invitees"] = invitees
        return attrs


class ProfileInvitationSentSerializer(serializers.Serializer):
    invitations = ProfileInvitationSerializer(many=True)
    emails_sent = serializers.IntegerField()
    emails_held = serializers.IntegerField()


class PublicInvitationSerializer(serializers.Serializer):
    profile_name = serializers.CharField()
    invited_email = serializers.EmailField()
    role = serializers.IntegerField()
    status = serializers.IntegerField()
    expires_at = serializers.DateTimeField(allow_null=True)


class InvitationSignupSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)


class InvitationResponseSerializer(serializers.Serializer):
    """The outcome of accepting or declining, for the invitee."""

    role = serializers.IntegerField()
    status = serializers.IntegerField()
    profile = JWTProfileSerializer()
    email = serializers.EmailField(source="invited_email")
