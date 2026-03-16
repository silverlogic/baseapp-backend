from __future__ import annotations

import graphene
import swapper
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .base_service import BaseProfilesService

Profile = swapper.load_model("baseapp_profiles", "Profile")


class GraphQLProfileService(BaseProfilesService):
    @property
    def service_name(self) -> str:
        return "profiles.graphql"

    def get_profile_object_type(self) -> graphene.ObjectType:
        return Profile.get_graphql_object_type()

    def get_profile_connection_edge(self) -> graphene.Connection.Edge:
        return self.get_profile_object_type()._meta.connection.Edge

    def create_profile_from_mutation(
        self, info: graphene.ResolveInfo, target_instance: models.Model, data: dict
    ) -> graphene.Connection.Edge:
        from baseapp_profiles.graphql.mutations import ProfileCreateSerializer

        content_type = ContentType.objects.get_for_model(target_instance._meta.model)
        profile_data = {
            "target_content_type": content_type.id,
            "target_object_id": target_instance.id,
            **data,
        }
        profile_serializer = ProfileCreateSerializer(
            data=profile_data, context={"request": info.context}
        )
        profile_serializer.is_valid(raise_exception=True)

        profile = profile_serializer.save()
        target_instance.profile = profile
        target_instance.save()
        return self.get_profile_connection_edge()(node=profile)
