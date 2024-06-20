import graphene
import swapper
from baseapp_core.graphql import (
    SerializerMutation,
    get_object_type_for_model,
    get_pk_from_relay_id,
    login_required,
)
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfileSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    name = serializers.CharField(required=True)

    class Meta:
        model = Profile
        fields = ("user", "name")


class ProfileCreate(SerializerMutation):
    profile = graphene.Field(lambda: Profile.get_graphql_object_type()._meta.connection.Edge)

    class Meta:
        serializer_class = ProfileSerializer

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        if not info.context.user.has_perm("baseapp_profiles.add_profile"):
            raise PermissionError(_("You don't have permission to create a profile"))

        return super().mutate_and_get_payload(root, info, **input)

    @classmethod
    def perform_mutate(cls, serializer, info):
        ProfileObjectType = Profile.get_graphql_object_type()
        obj = serializer.save()
        return cls(
            errors=None,
            profile=ProfileObjectType._meta.connection.Edge(node=obj),
        )


class ProfileEdit(SerializerMutation):
    profile = graphene.Field(get_object_type_for_model(Profile))

    class Meta:
        serializer_class = ProfileSerializer

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    def get_serializer_kwargs(cls, root, info, **input):
        pk = get_pk_from_relay_id(input.get("id"))
        instance = Profile.objects.get(pk=pk)
        if not info.context.user.has_perm("baseapp_profiles.change_profile", instance):
            raise PermissionError(_("You don't have permission to edit this profile"))
        return {
            "instance": instance,
            "data": input,
            "partial": True,
            "context": {"request": info.context},
        }

    @classmethod
    def perform_mutate(cls, serializer, info):
        obj = serializer.save()
        return cls(
            errors=None,
            profile=obj,
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        return super().mutate_and_get_payload(root, info, **input)


class ProfilesMutations(object):
    profile_create = ProfileCreate.Field()
    profile_edit = ProfileEdit.Field()
