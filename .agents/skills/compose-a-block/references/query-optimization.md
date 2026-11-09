# Query Optimization: optimizer hints on types and fields

A GraphQL query returns correct data whether or not it is optimized. The only symptom of a missing
optimization is the query count — so N+1s here are silent, and they are found by tests
(`query-count-tests.md`) or by reading the SQL log, never by a failing assertion elsewhere.

## The optimizer

`build_schema` (`baseapp_core/strawberry/schema.py`) installs strawberry-django's
`DjangoOptimizerExtension` on every schema. It walks the selection set and turns it into
`only()`, `select_related()`, `prefetch_related()` and `annotate()` on the root queryset, at every
nesting level, including connections and nested connections of the same type.

You do not call it. You **declare hints** where the walker can't infer what a resolver needs:

| Hint | Where | Use for |
|---|---|---|
| `only=[...]` | `django_type(...)` or `strawberry_django.field(...)` | columns a resolver or permission check reads but GraphQL doesn't expose |
| `select_related=[...]` | field | to-one paths a resolver walks |
| `prefetch_related=[...]` or `lambda info: Prefetch(...)` | field | to-many or virtual relations a resolver walks |
| `annotate={"_alias": lambda info: expr}` | field | annotations a resolver reads |

A hint on a field applies only when that field is selected. A hint on the type applies whenever
the type is loaded.

## The relay-id hint

`Node.id` carries `PublicIdOptimizerStore` (`baseapp_core/strawberry/types.py`). When `id` is
selected it annotates `mapped_public_id` for the model behind the type, at any nesting level:

```python
return {
    "mapped_public_id": Subquery(
        DocumentId.objects.filter(
            content_type=ContentType.objects.get_for_model(model_cls),
            object_id=OuterRef("pk"),
        ).values("public_id")
    )
}
```

This is the highest-leverage anti-N+1 mechanism in the repo: without it, resolving the relay `id`
on every node in every connection is one `DocumentId` lookup per row. It is automatic for every type
whose last base is `Node`. A queryset you build by hand (a `Prefetch` inside a hint) gets it only if
you pass it through `optimize(queryset, info)` — see Pattern C.

## Pattern A — `only=` for columns GraphQL doesn't expose

The optimizer defers any column not selected. If a resolver, a permission backend, or Django's own
prefetch machinery reads such a column, each access becomes a per-row `refresh_from_db`.

`baseapp_chats/strawberry/types.py`:

```python
# room_id: the prefetch pipeline maps messages back to their room; deleted, message_type,
# profile_id: `content` branches on them.
@django_type(
    Message,
    filterset_class=MessageFilter,
    relations=("user", "profile", "room", "in_reply_to"),
    only=["room_id", "deleted", "message_type", "profile_id", "extra_data", "content"],
)
class MessageType(*strawberry_shared_interfaces.get("MentionsInterface"), Node):
    ...
```

Prefer the field when only one resolver needs the column (`baseapp_auth/strawberry/types.py`):

```python
    @strawberry_django.field(only=["email"])
    def email(self, info: Info) -> str | None:
        return view_user_private_field(self, info, "email")
```

The rule: **any model column your resolvers read but GraphQL does not expose goes in `only=`.**
Models with two FKs to the same parent (`actor` / `target`) need both `_id` columns there:
`@django_type(Block, only=["actor_id", "target_id"], ...)`.

## Pattern B — annotations on the field that reads them

`baseapp_comments/strawberry/interfaces.py`:

```python
def _metadata_annotation(name: str) -> dict[str, Callable[[Info], Any]]:
    def annotation(info: Info) -> Any:
        service = shared_services.get("commentable_metadata")
        return service.get_annotations(model_from_info(info))[name]

    return {name: annotation}


@strawberry.interface(name="CommentsInterface")
class CommentsInterface(Node):
    @strawberry_django.field(annotate=_metadata_annotation("_commentable_comments_count"))
    def comments_count(self, info: Info) -> CommentsCount: ...
```

`model_from_info(info)` returns the model behind the type that owns the field, so one interface
field annotates `Profile`, `Page` or `Comment` rows correctly. Never annotate unconditionally in
`get_queryset` what only one field reads.

## Pattern C — virtual relations through `DocumentId`

A `Follow` points at actor and target through `DocumentId`. A callable `prefetch_related` hint
batches the documents and their `content_object`, optimizing each target queryset for the
selection under the field (`baseapp_follows/strawberry/types.py`):

```python
def document_prefetch(attr: str, models=None) -> Callable[[Info], Prefetch]:
    def prefetch(info: Info) -> Prefetch:
        querysets = [optimize(m._default_manager.all(), info) for m in (models or [Profile])]
        documents = DocumentId.objects.select_related("content_type").prefetch_related(
            GenericPrefetch("content_object", querysets)
        )
        return Prefetch(attr, queryset=documents)

    return prefetch


    @strawberry_django.field(
        graphql_type=Optional[Node],
        only=["actor_id"],
        prefetch_related=document_prefetch("actor"),
    )
    def actor_object(self, info: Info) -> Any:
        return resolve_document_content_object(self.actor, info)
```

`optimize(queryset, info)` inside the hint is what gives the prefetched profiles their
`mapped_public_id` and interface annotations. Content types not pre-warmed fall back to the
request-scoped cache in `resolve_document_content_object` (`baseapp_core/graphql/utils.py`).

Simpler GFK targets: `prefetch_related=["target_document__content_object"]` plus
`only=["target_document_id"]` (`baseapp_reports`, `baseapp_ratings`).

## Where else logic can live

| Hook | Use for |
|---|---|
| optimizer hints | Optimization. |
| `get_queryset(cls, queryset, info, **kwargs)` classmethod | **Visibility and permissions** for root lists, node lookups and to-many connections. Not applied to to-one traversals, which stay joined (`baseapp_core/strawberry/optimizer.py`). |
| `get_node(cls, info, pk)` classmethod | Per-object permission check. Call `super().get_node(info, pk)` first, then check. |
| resolver body | Business logic. Return querysets; never evaluate them to decide what to optimize. |

## Anti-patterns

- A resolver that reads a deferred column with no `only=` hint. Silent per-row
  `refresh_from_db`.
- Passing a lazy type (`type_for_model(...)`) as `graphql_type=` to `strawberry_django.field` —
  crashes at class creation. Use a plain annotation, or `@strawberry.field(graphql_type=...)`.
- Plain `strawberry.field` resolvers that touch the ORM on anything a subscription can reach. Use
  `strawberry_django.field` (async-safe through `django_resolver`).
- Building a `Prefetch` queryset by hand without `optimize(queryset, info)` — the nested level
  loses its relay-id annotation and interface hints.
- Unconditional `annotate_queryset` in `get_queryset` for something only one field reads. Put the
  annotation on that field.
- Assuming a resolver's field reads are free because the field "is on the model". If GraphQL
  doesn't select it, it is deferred.
