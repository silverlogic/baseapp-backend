import graphene
import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from graphene_django.types import ErrorType
from graphql.error import GraphQLError
from rest_framework import serializers

from baseapp_core.graphql import SerializerMutation, login_required
from baseapp_profiles.graphql.mutations import ProfileCreateSerializer

Organization = swapper.load_model("baseapp_organizations", "Organization")
Profile = swapper.load_model("baseapp_profiles", "Profile")
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
    profile = graphene.Field(lambda: Profile.get_graphql_object_type()._meta.connection.Edge)

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

        if apps.is_installed("baseapp_profiles"):
            content_type = ContentType.objects.get_for_model(Organization)

            ProfileObjectType = Profile.get_graphql_object_type()
            profile_data = {
                "target_content_type": content_type.id,
                "target_object_id": obj.id,
                "name": name,
                "url_path": url_path,
            }
            profile_serializer = ProfileCreateSerializer(
                data=profile_data, context={"request": info.context}
            )
            if profile_serializer.is_valid():
                profile = profile_serializer.save()
                obj.profile = profile
                obj.save()
                return cls(
                    organization=OrganizationObjectType._meta.connection.Edge(node=obj),
                    profile=ProfileObjectType._meta.connection.Edge(node=profile),
                )
            else:
                errors = ErrorType.from_errors(profile_serializer.errors)
                return cls(
                    errors=errors,
                )
        return cls(
            organization=OrganizationObjectType._meta.connection.Edge(node=obj),
        )


class OrganizationsMutations(object):
    organization_create = OrganizationCreate.Field()
