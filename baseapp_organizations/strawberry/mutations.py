import strawberry
import swapper
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError
from rest_framework import serializers
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    ErrorType,
    RelayMutationInput,
    RelayMutationPayload,
    relay_mutation,
    type_for_model,
)
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.mutations import (
    add_request_files,
    input_data,
    serializer_errors,
)

from .types import OrganizationLazyType

Organization = swapper.load_model("baseapp_organizations", "Organization")
app_label = Organization._meta.app_label
Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileLazyType = type_for_model(Profile)


class BaseOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ()


class OrganizationCreateSerializer(BaseOrganizationSerializer):
    name = serializers.CharField(required=True)
    url_path = serializers.SlugField(required=False)

    class Meta(BaseOrganizationSerializer.Meta):
        fields = BaseOrganizationSerializer.Meta.fields + (
            "name",
            "url_path",
        )


@strawberry.input(name="OrganizationCreateInput")
class OrganizationCreateInput(RelayMutationInput):
    name: str
    url_path: str | None = UNSET


@strawberry.type(name="OrganizationCreatePayload")
class OrganizationCreatePayload(RelayMutationPayload):
    organization: Edge[OrganizationLazyType] | None = None
    profile: Edge[ProfileLazyType] | None = None


@strawberry.type
class OrganizationsMutations:
    @relay_mutation(login_required=True)
    def organization_create(
        self, info: Info, input: OrganizationCreateInput
    ) -> OrganizationCreatePayload | None:
        if not info.context.user.has_perm(f"{app_label}.add_organization"):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )

        serializer = OrganizationCreateSerializer(
            data=add_request_files(info, input_data(input)), context={"request": info.context}
        )
        if not serializer.is_valid():
            return OrganizationCreatePayload(errors=serializer_errors(serializer))

        name = serializer.validated_data.get("name")
        url_path = serializer.validated_data.pop("url_path", None)
        obj = serializer.save()
        organization = Edge(node=obj, cursor=None)

        if service := shared_services.get("profiles.graphql"):
            try:
                profile = service.create_profile_from_mutation(
                    info, obj, {"name": name, "url_path": url_path}
                )
            except serializers.ValidationError as error:
                return OrganizationCreatePayload(
                    errors=[
                        ErrorType(field=field, messages=[str(m) for m in messages])
                        for field, messages in error.detail.items()
                    ]
                )
            return OrganizationCreatePayload(organization=organization, profile=profile)

        return OrganizationCreatePayload(organization=organization)
