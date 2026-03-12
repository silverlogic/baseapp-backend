import graphene
import swapper
from django.utils.translation import gettext_lazy as _
from graphene_django.types import ErrorType
from graphql.error import GraphQLError
from rest_framework import serializers

from baseapp_core.graphql import SerializerMutation, login_required
from baseapp_core.plugins import shared_service_registry

Organization = swapper.load_model("baseapp_organizations", "Organization")
app_label = Organization._meta.app_label


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


class OrganizationCreate(SerializerMutation):
    organization = graphene.Field(
        lambda: Organization.get_graphql_object_type()._meta.connection.Edge
    )
    profile = graphene.Field(
        lambda: shared_service_registry.get_service(
            "profiles.graphql"
        ).get_profile_connection_edge()
    )

    class Meta:
        serializer_class = OrganizationCreateSerializer

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        if not info.context.user.has_perm(f"{app_label}.add_organization"):
            raise GraphQLError(
                str(_("You don't have permission to perform this action")),
                extensions={"code": "permission_required"},
            )
        response = super().mutate_and_get_payload(root, info, **input)
        return response

    @classmethod
    def perform_mutate(cls, serializer, info):
        OrganizationObjectType = Organization.get_graphql_object_type()

        if not serializer.is_valid():
            errors = ErrorType.from_errors(serializer.errors)
            return cls(
                errors=errors,
            )

        name = serializer.validated_data.get("name")
        url_path = serializer.validated_data.pop("url_path", None)

        obj = serializer.save()

        if service := shared_service_registry.get_service("profiles.graphql"):
            try:
                profile_edge = service.create_profile_from_mutation(
                    info,
                    obj,
                    {
                        "name": name,
                        "url_path": url_path,
                    },
                )
                return cls(
                    organization=OrganizationObjectType._meta.connection.Edge(node=obj),
                    profile=profile_edge,
                )
            except serializers.ValidationError as e:
                errors = ErrorType.from_errors(e.detail)
                return cls(
                    errors=errors,
                )

        return cls(
            organization=OrganizationObjectType._meta.connection.Edge(node=obj),
        )


class OrganizationsMutations(object):
    organization_create = OrganizationCreate.Field()
