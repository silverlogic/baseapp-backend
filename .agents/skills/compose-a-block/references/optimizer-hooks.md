# Field-Level Optimizer Hints

A hint on `django_type(...)` optimizes *a type*. A hint on a field optimizes *a field* — and the
optimizer applies it only when that field is actually selected.

Reach for field hints when a field lives on a **shared GraphQL interface**. An interface is
implemented by many types across many blocks; requiring each of them to add the right `only=` or
annotation is both a coupling problem and a reliability problem. Attaching the hint to the field
means consumers wire up nothing — Strawberry copies interface fields, hints included, into every
implementing type.

## When to use which

| Situation | Mechanism |
|---|---|
| Column this specific type always needs | `django_type(..., only=[...])` |
| Field on a shared interface, consumed by other blocks' types | field hint |
| Expensive annotation only some queries want | field `annotate=` — pay per selection |
| Relation with no direct FK, reached through `DocumentId` | field `prefetch_related=lambda info: Prefetch(...)` |

## Pattern A — conditional annotation

`baseapp_blocks/strawberry/types.py`:

```python
def _metadata_annotation(name: str, builder: str) -> dict[str, Callable[[Info], Any]]:
    """Optimizer hint: annotate the count subquery on whatever model implements the interface."""

    def annotation(info: Info) -> Any:
        service = shared_services.get("blockable_metadata")
        return getattr(service, builder)(model_from_info(info))

    return {name: annotation}


@strawberry.interface(name="BlocksInterface")
class BlocksInterface(Node):
    @strawberry_django.field(
        annotate=_metadata_annotation("_blockable_blockers_count", "_blockers_count_subquery")
    )
    def blockers_count(self, info: Info) -> int | None:
        if info.context.user.has_perm("baseapp_blocks.view_block-blockers_count", self):
            return shared_services.get("blockable_metadata").get_blockers_count(self)
        return None
```

The shape to copy:

1. The hint value is a callable taking `info`; it runs at optimization time.
2. Build the subquery from `model_from_info(info)` — the field is generic across every implementing
   type.
3. The resolver reads the annotation through the service getter, which falls back to a query when
   the annotation is absent (`annotate-queryset.md`).

Same pattern in `baseapp_comments`, `baseapp_follows`, `baseapp_reactions`, `baseapp_ratings` and
`baseapp_mentions` interfaces.

## Pattern B — prefetching a virtual relation

The hardest case. `mentions` is a connection on any commentable/postable object, but there is no FK
from the consumer to `Mention` — the link runs through `DocumentId`. A callable `prefetch_related`
hint registers the `document__<reverse>` path as a real prefetch, paginated per parent
(`baseapp_mentions/strawberry/interfaces.py`):

```python
def _mentions_prefetch(info: Info) -> Prefetch:
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


@strawberry.interface(name="MentionsInterface")
class MentionsInterface(Node):
    @connection(CountedConnection[MentionLazyType] | None, prefetch_related=_mentions_prefetch)
    def mentions(self, info: Info) -> Iterable[Model]:
        docs = self.document.all() if hasattr(self, "document") else None
        if docs is not None and (doc := next(iter(docs), None)) is not None:
            return getattr(doc, Mention.target_document_accessor()).all()
        ...
```

Non-obvious requirements:

- **`optimize(queryset, info)` the prefetched queryset.** That is what applies the selection under
  the field, including the relay-id annotation. A raw queryset loses both.
- **For connections, window-paginate and `mark_optimized_by_prefetching`**, so the resolver's
  queryset is served from the prefetch cache instead of re-queried per parent.
- **The resolver must read the prefetched path** (`self.document.all()` …), with a fallback query
  for non-optimized paths (subscriptions, mutation payloads).
- **The consuming model must expose `document = GenericRelation(DocumentId)`** so the reverse path
  is a real Django prefetch path. `DocumentIdMixin` declares it.

## Hints on plain `strawberry.field`

Fields whose return type is a lazy type can't be `strawberry_django.field(graphql_type=Lazy)` (it
crashes at class creation). Declare them with `@strawberry.field(graphql_type=Optional[Lazy])` and,
if they need a hint, set the field's `.store` after the class is defined — see `Node.id`
(`baseapp_core/strawberry/relay.py`) and `_MetadataOptimizerStore` in
`baseapp_pages/strawberry/interfaces.py`.

## Documenting the contract

Interfaces that carry their own optimization should say so, so consumers don't duplicate it:

> Mentions fields for any DocumentId-aware model. Optimizer hints live on the fields.

## Anti-patterns

- Building the subquery from a hardcoded model instead of `model_from_info(info)`. The field runs
  for every implementing type.
- A `Prefetch` hint whose queryset isn't passed through `optimize(...)` — the most common cause of
  "I added the prefetch and the count barely moved".
- A connection prefetch without window pagination / `mark_optimized_by_prefetching` — the resolver
  ignores the prefetch and queries per parent.
- Putting interface optimization into each consuming type's `only=` / `get_queryset`. It reverses
  the dependency direction the plugin architecture exists to prevent.
