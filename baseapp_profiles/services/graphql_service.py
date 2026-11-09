from __future__ import annotations

from typing import TYPE_CHECKING, Any

import swapper
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .base_service import BaseProfilesService

if TYPE_CHECKING:
    from strawberry.types import Info

    from baseapp_core.strawberry.connections import Edge

Profile = swapper.load_model("baseapp_profiles", "Profile")


class GraphQLProfileService(BaseProfilesService):
    @property
    def service_name(self) -> str:
        return "profiles.graphql"

    def get_profile_type(self) -> Any:
        """The Strawberry type registered for the (possibly swapped) Profile model."""
        from baseapp_core.strawberry.registry import type_registry

        return type_registry.get_type_for_model(Profile)

    def create_profile_from_mutation(
        self, info: Info, target_instance: models.Model, data: dict
    ) -> Edge:
        """Create the profile of `target_instance` and link it; raises DRF `ValidationError`."""
        from baseapp_core.strawberry.connections import Edge
        from baseapp_profiles.strawberry.serializers import ProfileCreateSerializer

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
        return Edge(node=profile, cursor=None)
