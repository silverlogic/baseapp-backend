# Query Optimization: `pre_optimization_hook`

A GraphQL query returns correct data whether or not it is optimized. The only symptom of a missing
optimization is the query count — so N+1s here are silent, and they are found by tests
(`query-count-tests.md`) or by reading the SQL log, never by a failing assertion elsewhere.

## Which library

Two packages with near-identical names are installed. Only one does anything.

| Library | Import | Version | Status |
|---|---|---|---|
| `graphene-django-query-optimizer` | `query_optimizer` | 0.10.15 | **Live.** Supplies `pre_optimization_hook`, `QueryOptimizer`, `OptimizationCompiler`, field-level `optimizer_hook`, `DjangoConnectionField`. |
| `graphene-django-optimizer` | `gql_optimizer` | 0.10.0 | **Dead.** 8 ObjectTypes in this repo mix in `gql_optimizer.OptimizedDjangoObjectType`, but `gql_optimizer.query()` — the call that would activate it — appears nowhere, nor does `resolver_hints`. `baseapp_core.DjangoObjectType` sits later in the MRO and supplies the working optimizer. |

**Do not copy the `OptimizedDjangoObjectType` mixin into new code.** It is inherited noise:

```python
# baseapp_blocks/graphql/object_types.py:108 — legacy shape, do not imitate
class BlockObjectType(
    BaseBlockObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
```

New ObjectTypes subclass `baseapp_core.graphql.DjangoObjectType` and nothing else.

## The base hook

`baseapp_core/graphql/object_types.py:31`. Every block inherits this.

```python
class DjangoObjectType(OptimizerDjangoObjectType):   # query_optimizer.DjangoObjectType

    @classmethod
    def pre_optimization_hook(
        cls, queryset: QuerySet[TModel], optimizer: QueryOptimizer
    ) -> QuerySet[TModel]:
        """
        A hook for modifying the optimizer results before optimization happens.
        Recursively sets annotations for optimizer and its related optimizers.
        Also checks only_fields to avoid unnecessary annotations.
        """

        def recursive_set_annotations(opt: QueryOptimizer, model_cls: TModel) -> None:
            # Only add the annotations if the id field is in the only_fields
            only_fields_set = set(opt.only_fields)
            if "id" in only_fields_set:
                new_ann = cls._get_annotations(model_cls)
                opt.annotations = {**(opt.annotations or {}), **new_ann}

            for related_opt in opt.select_related.values():
                recursive_set_annotations(related_opt, related_opt.model)

            for related_opt in opt.prefetch_related.values():
                recursive_set_annotations(related_opt, related_opt.model)

        recursive_set_annotations(optimizer, queryset.model)

        return super().pre_optimization_hook(queryset, optimizer)
```

What it injects is the relay-id subquery
(`baseapp_core/hashids/strategies/public_id/queryset_annotator.py`):

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
on every node in every connection is one `DocumentId` lookup per row.

Two consequences you must respect:

- **The annotation is gated on `"id" in optimizer.only_fields`.** If you build a child
  `QueryOptimizer` by hand (see `optimizer-hooks.md`) and forget to append `"id"` to its
  `only_fields`, that level silently loses `mapped_public_id` and goes back to per-row lookups.
- **Always call `super().pre_optimization_hook(queryset, optimizer)`** in an override, or you drop
  the relay-id annotation for the whole type.

## Signature and contract

```python
@classmethod
def pre_optimization_hook(cls, queryset, optimizer) -> QuerySet: ...
```

You get two things and may modify both:

| Object | What to do with it |
|---|---|
| `queryset` | Apply `select_related` / `prefetch_related` / `annotate`. Return it. |
| `optimizer` | Mutate `only_fields`, `related_fields`, `annotations`, `select_related`, `prefetch_related`. The return value is ignored — mutate in place. |

**The queryset is still lazy here, and must stay that way.** Do not call `len()`, iterate, or
`.exists()` on it. You cannot inspect the rows to decide what to optimize — the `baseapp_follows`
README states this constraint explicitly for content-type discovery. Decide from the model and the
optimizer, never from the data.

## Pattern A — force deferred columns into `only_fields`

The optimizer defers any column not surfaced through GraphQL. If a resolver or Django's own
prefetch machinery reads such a column, each access becomes a per-row `refresh_from_db`.

`baseapp_chats/graphql/object_types.py:85` — the clearest example in the repo:

```python
    @classmethod
    def pre_optimization_hook(
        cls, queryset: QuerySet[TModel], optimizer: QueryOptimizer
    ) -> QuerySet[TModel]:
        """Preload three columns the optimizer would otherwise defer.

        - `room_id`: when `chatRoom.allMessages` is evaluated, Django's
          prefetch pipeline reads `message.room_id` to map children
          back to their parent. If it's not in `only_fields`, every
          message triggers `refresh_from_db(['room_id'])` (N round trips).
        - `deleted`, `message_type`: `resolve_content` branches on both
          before returning `root.content`. They live on the model but
          aren't surfaced through GraphQL, so they get deferred and
          each access fans out as a per-row `refresh_from_db`.
        """
        for field_name in ("room_id", "deleted", "message_type"):
            if field_name not in optimizer.only_fields:
                optimizer.only_fields.append(field_name)
        return super().pre_optimization_hook(queryset, optimizer)
```

The rule: **any model field your resolvers read but GraphQL does not expose must be added to
`only_fields`.** They are scalars; loading them unconditionally is far cheaper than the AST walk
needed to gate on what the caller asked for.

## Pattern B — `select_related` + annotations + reaching into a child optimizer

`baseapp_comments/graphql/object_types.py:157`:

```python
    @classmethod
    def pre_optimization_hook(cls, queryset, optimizer) -> models.QuerySet:
        queryset = super().pre_optimization_hook(queryset, optimizer)
        queryset = queryset.select_related("target_document", "target_document__content_type")

        # Required for CommentsInterface.resolve_comments checks (no longer a column).
        required_fields = ["id", "target_document_id", "in_reply_to_id", "status"]
        optimizer.only_fields.extend(required_fields)
        if "comments" in optimizer.prefetch_related:
            required_fields_set = set(
                [*optimizer.prefetch_related["comments"].only_fields, "status"]
            )
            optimizer.prefetch_related["comments"].only_fields = list(required_fields_set)

        # Annotate commentable metadata (includes replies_count_total for CommentFilter).
        if service := shared_services.get("commentable_metadata"):
            queryset = service.annotate_queryset(queryset)

        # Annotate reactable metadata (includes reactions_count_total for CommentFilter).
        if service := shared_services.get("reactable_metadata"):
            queryset = service.annotate_queryset(queryset)

        return queryset
```

Three things worth copying: `super()` first; the child optimizer at
`optimizer.prefetch_related["comments"]` is reachable and mutable; service lookups are always
`None`-guarded with the walrus so the block still works when the other block isn't installed.

## Pattern C — service annotations only

The most common override is a few lines. `baseapp_profiles/graphql/object_types.py:205`:

```python
    @classmethod
    def pre_optimization_hook(cls, queryset, optimizer) -> "QuerySet[Profile]":
        queryset = super().pre_optimization_hook(queryset, optimizer)
        if service := shared_services.get("commentable_metadata"):
            queryset = service.annotate_queryset(queryset)
        if service := shared_services.get("followable_metadata"):
            queryset = service.annotate_queryset(queryset)
        if service := shared_services.get("reportable_metadata"):
            queryset = service.annotate_queryset(queryset)
        return queryset
```

Same shape at `baseapp_auth/graphql/object_types.py:131` and `baseapp_pages/graphql/object_types.py:165`.

## Pattern D — GenericPrefetch through DocumentId

The heaviest case, `baseapp_follows/graphql/object_types.py:49`. A `Follow` points at actor and
target through `DocumentId`, so `resolve_actor_object` would otherwise fire two queries per row.
`GenericPrefetch` (Django 5.0+) declares which model queryset to use per content type, and the
prefetched queryset is itself annotated so the *nested* resolvers don't N+1 either:

```python
        profile_strategy = get_hashids_strategy_from_instance_or_cls(Profile)
        profile_qs = Profile.objects.annotate(
            **profile_strategy.queryset_annotator.get_annotations(Profile)
        )
        if service := shared_services.get("followable_metadata"):
            profile_qs = service.annotate_queryset(profile_qs)

        document_qs = DocumentId.objects.select_related("content_type").prefetch_related(
            GenericPrefetch("content_object", [profile_qs]),
        )
        queryset = queryset.prefetch_related(
            Prefetch("actor", queryset=document_qs),
            Prefetch("target", queryset=document_qs),
        )

        for required in ("id", "actor_id", "target_id"):
            if required not in optimizer.only_fields:
                optimizer.only_fields.append(required)
        return queryset
```

Note the manual `mapped_public_id` annotation on `profile_qs`: the recursive walker in the base
hook only reaches optimizers it knows about, and a hand-built `GenericPrefetch` queryset isn't one
of them. Content types other than the pre-warmed one fall back to the request-scoped cache in
`resolve_document_content_object` (`baseapp_core/graphql/utils.py:73`).

## Where else optimization can live

| Hook | Use for |
|---|---|
| `pre_optimization_hook` | Optimization. Runs inside the optimizer with access to `optimizer`. |
| `get_queryset(cls, queryset, info)` | **Visibility and permissions**, not optimization — it has no optimizer. A few types also annotate here when the type is reached through a non-optimized path (`baseapp/content_feed/graphql/object_types.py:63`). |
| `get_node(cls, info, node_id)` | Per-object permission check. Always call `super()` first, then check. |
| field `optimizer_hook` | Interface fields — see `optimizer-hooks.md`. |

## Anti-patterns

- Overriding `pre_optimization_hook` without calling `super()`. Drops `mapped_public_id` and puts
  a `DocumentId` lookup back on every row.
- Evaluating the queryset inside the hook (`len()`, iteration, `.exists()`) to decide what to
  optimize. Defeats the optimizer and breaks pagination.
- Adding `gql_optimizer.OptimizedDjangoObjectType` to a new ObjectType because neighbours have it.
  It does nothing.
- Optimizing the ObjectType and leaving the connection field as `DjangoFilterConnectionField` —
  the hook never runs. See `connection-fields.md`.
- Putting an interface's optimization in each consuming type's hook instead of on the field. See
  `optimizer-hooks.md`.
- Assuming a resolver's field reads are free because the field "is on the model". If GraphQL
  doesn't select it, it is deferred.
