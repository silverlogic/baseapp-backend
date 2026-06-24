import graphene
import swapper
from query_optimizer import DjangoConnectionField

from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.plugins import shared_services

from ..services import mentions_reverse_name

Mention = swapper.load_model("baseapp_mentions", "Mention")
Profile = swapper.load_model("baseapp_profiles", "Profile")


def _resolve_target_doc_pk(obj) -> int | None:
    """Return the consuming object's DocumentId pk, preferring annotation."""
    doc_id = getattr(obj, "_mention_target_doc_id", None)
    if doc_id is not None:
        return doc_id
    doc = DocumentId.get_or_create_for_object(obj)
    return doc.pk if doc is not None else None


# The `*_optimizer_hook` functions below are attached to each field's
# `optimizer_hook` attribute. The query optimizer calls them during AST
# compilation only when the matching field is selected in the GraphQL
# query, so the extra annotation or prefetch the resolver needs is added
# on demand — never paid for on queries that don't touch the field, and
# without requiring every consuming ObjectType to wire it up in its own
# `pre_optimization_hook`.


def _mentions_optimizer_hook(compiler) -> None:
    """Walk the parent optimizer through `document__<reverse>` so the
    `mentions` connection is loaded via a real `prefetch_related` chain.
    """
    if service := shared_services.get("mentionable_metadata"):
        service.prefetch_mentions_in_optimizer_compiler(compiler)


def _mentions_count_optimizer_hook(compiler) -> None:
    """Attach `_mentions_count` on the parent optimizer only when
    `mentionsCount` is selected.
    """
    if service := shared_services.get("mentionable_metadata"):
        service.annotate_mentions_count_in_optimizer_compiler(compiler)


def _is_mentioning_profile_optimizer_hook(compiler) -> None:
    """Attach `_mention_target_doc_id` on the parent optimizer only when
    `isMentioningProfile` is selected, so the resolver can issue its
    per-row `.exists()` without first looking up the DocumentId.
    """
    if service := shared_services.get("mentionable_metadata"):
        service.annotate_target_doc_id_in_optimizer_compiler(compiler)


class MentionsInterface(RelayNode):
    """GraphQL fields exposed on any object type that has mentioned profiles.

    Consuming object types (Comment, ContentPost, Message, ...) opt in by
    name via the GraphQL shared interface registry:

        interfaces = graphql_shared_interfaces.get(RelayNode, "MentionsInterface")

    The consuming model must expose a `document` `GenericRelation` to
    `baseapp_core.DocumentId` so the optimizer can walk `document__<reverse>`
    as a real Django prefetch path. (`DocumentIdMixin` already declares it,
    so any consumer that inherits the mixin gets this for free.)

    All optimizer wiring lives on the fields below — consumers do not need
    to add anything to their own `pre_optimization_hook`.
    """

    mentions = DjangoConnectionField(get_object_type_for_model(Mention))
    mentions_count = graphene.Field(graphene.Int)
    is_mentioning_profile = graphene.Field(graphene.Boolean, profile_id=graphene.ID(required=True))
    mentions.optimizer_hook = _mentions_optimizer_hook
    mentions_count.optimizer_hook = _mentions_count_optimizer_hook
    is_mentioning_profile.optimizer_hook = _is_mentioning_profile_optimizer_hook

    def resolve_mentions(root, info, **kwargs):
        # Hit the prefetch cache populated by the optimizer hook above when
        # the consumer was paged via the optimizer.
        try:
            docs = root.document.all()
        except AttributeError:
            docs = None

        if docs is not None:
            doc = next(iter(docs), None)
            if doc is not None:
                return getattr(doc, mentions_reverse_name()).all()

        # Fallback for unannotated calls
        doc_pk = _resolve_target_doc_pk(root)
        if doc_pk is None:
            return Mention.objects.none()
        return Mention.objects.filter(target_document_id=doc_pk).select_related("profile")

    def resolve_mentions_count(root, info):
        if service := shared_services.get("mentionable_metadata"):
            return service.get_mentions_count(root)
        return 0

    def resolve_is_mentioning_profile(root, info, profile_id):
        try:
            pk = get_pk_from_relay_id(profile_id)
        except Exception:  # noqa: BLE001 — malformed IDs are treated as "not mentioning"
            return False
        if pk is None:
            return False
        doc_pk = _resolve_target_doc_pk(root)
        if doc_pk is None:
            return False
        return Mention.objects.filter(target_document_id=doc_pk, profile_id=pk).exists()
