import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node, get_object_type_for_model

Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfilesQueries:
    all_profiles = DjangoFilterConnectionField(get_object_type_for_model(Profile))
    profile = Node.Field(get_object_type_for_model(Profile))
