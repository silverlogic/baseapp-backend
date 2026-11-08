from collections.abc import Iterable
from typing import Any

import strawberry
import strawberry_django
import swapper
from django.db.models import Model, Prefetch
from graphql.execution.values import get_argument_values
from graphql_relay import cursor_to_offset, offset_to_cursor
from strawberry.relay.utils import SliceMetadata
from strawberry.types import Info
from strawberry_django.optimizer import (
    OptimizerStore,
    mark_optimized_by_prefetching,
    optimize,
)
from strawberry_django.pagination import apply_window_pagination

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import CountedConnection, Node, model_from_info
from baseapp_core.strawberry.connections import Edge, connection

from .types import MentionLazyType

Mention = swapper.load_model("baseapp_mentions", "Mention")


def _resolve_target_doc_pk(obj: Model) -> int | None:
    doc_id = getattr(obj, "_mention_target_doc_id", None)
    if doc_id is not None:
        return doc_id
    doc = DocumentId.get_or_create_for_object(obj)
    return doc.pk if doc is not None else None


def _connection_slice(info: Info) -> SliceMetadata:
    """The page a connection field's arguments select, `offset` folded in like at resolve time."""
    raw = info._raw_info
    args = get_argument_values(
        raw.parent_type.fields[raw.field_name], raw.field_nodes[0], raw.variable_values
    )
    after = args.get("after")
    if offset := args.get("offset"):
        if after:
            offset += cursor_to_offset(after) + 1
        after = offset_to_cursor(offset - 1)
    return SliceMetadata.from_arguments(
        info,
        first=args.get("first"),
        last=args.get("last"),
        before=args.get("before"),
        after=after,
        prefix=Edge.CURSOR_PREFIX,
    )


def _mentions_prefetch(info: Info) -> Prefetch:
    """Batch the virtual `document__<reverse>` relation, paginated per parent like a relation."""
    queryset = optimize(
        Mention.objects.all(), info, store=OptimizerStore.with_hints(only=["target_document_id"])
    )
    page = _connection_slice(info)
    queryset = apply_window_pagination(
        queryset,
        related_field_id="target_document_id",
        offset=page.start,
        limit=page.end - page.start,
    )
    return Prefetch(
        Mention.document_prefetch_path(), queryset=mark_optimized_by_prefetching(queryset)
    )


def _metadata_annotation(builder: str) -> Any:
    def annotation(info: Info) -> Any:
        service = shared_services.get("mentionable_metadata")
        return getattr(service, builder)(model_from_info(info))

    return annotation


@strawberry.interface(name="MentionsInterface")
class MentionsInterface(Node):
    """Mentions fields for any DocumentId-aware model. Optimizer hints live on the fields."""

    @connection(CountedConnection[MentionLazyType] | None, prefetch_related=_mentions_prefetch)
    def mentions(self, info: Info) -> Iterable[Model]:
        docs = self.document.all() if hasattr(self, "document") else None
        if docs is not None and (doc := next(iter(docs), None)) is not None:
            return getattr(doc, Mention.target_document_accessor()).all()
        doc_pk = _resolve_target_doc_pk(self)
        if doc_pk is None:
            return Mention.objects.none()
        return Mention.objects.filter(target_document_id=doc_pk)

    @strawberry_django.field(
        annotate={"_mentions_count": _metadata_annotation("_mentions_count_subquery")}
    )
    def mentions_count(self, info: Info) -> int | None:
        if service := shared_services.get("mentionable_metadata"):
            return service.get_mentions_count(self)
        return 0

    @strawberry_django.field(
        annotate={"_mention_target_doc_id": _metadata_annotation("_target_doc_id_subquery")}
    )
    def is_mentioning_profile(self, info: Info, profile_id: strawberry.ID) -> bool | None:
        try:
            pk = get_pk_from_relay_id(profile_id)
        except Exception:  # noqa: BLE001 — malformed IDs are treated as "not mentioning"
            return False
        if pk is None:
            return False
        doc_pk = _resolve_target_doc_pk(self)
        if doc_pk is None:
            return False
        return Mention.objects.filter(target_document_id=doc_pk, profile_id=pk).exists()
