from baseapp_core.graphql import Node
from graphene_django.filter import DjangoFilterConnectionField

from .object_types import ProfileObjectType


class ProfilesQueries:
    all_profiles = DjangoFilterConnectionField(ProfileObjectType)
    profile = Node.Field(ProfileObjectType)
