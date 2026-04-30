import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id
from baseapp_core.models import DocumentId

Mention = swapper.load_model("baseapp_mentions", "Mention")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class MentionsInterface(RelayNode):
    """GraphQL fields exposed on any object type that has mentioned profiles.

    Consuming object types (Comment, ContentPost, Message, ...) append this
    interface conditionally:

        if apps.is_installed("baseapp_mentions"):
            from baseapp_mentions.graphql.interfaces import MentionsInterface
            interfaces.append(MentionsInterface)

    No fields are added to the consuming model — the resolvers query the
    Mention through-table keyed off the consuming object's DocumentId.
    """

    mentioned_profiles = DjangoFilterConnectionField(get_object_type_for_model(Profile))
    mentions_count = graphene.Int()
    is_mentioning_profile = graphene.Boolean(profile_id=graphene.ID(required=True))

    def resolve_mentioned_profiles(self, info, **kwargs):
        doc = DocumentId.get_or_create_for_object(self)
        profile_pks = Mention.objects.filter(target=doc).values_list("profile_id", flat=True)
        return gql_optimizer.query(Profile.objects.filter(pk__in=profile_pks), info)

    def resolve_mentions_count(self, info):
        doc = DocumentId.get_or_create_for_object(self)
        return Mention.objects.filter(target=doc).count()

    def resolve_is_mentioning_profile(self, info, profile_id):
        doc = DocumentId.get_or_create_for_object(self)
        try:
            pk = get_pk_from_relay_id(profile_id)
        except Exception:  # noqa: BLE001 — malformed IDs are treated as "not mentioning"
            return False
        if pk is None:
            return False
        return Mention.objects.filter(target=doc, profile_id=pk).exists()
