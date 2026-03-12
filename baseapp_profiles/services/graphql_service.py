from __future__ import annotations

import graphene
import swapper
from django.db import models

from baseapp_core.models import DocumentId
from baseapp_profiles.graphql.mutations import ProfileCreateSerializer

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
        profile_data = {
            "target": DocumentId.get_or_create_for_object(target_instance),
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
