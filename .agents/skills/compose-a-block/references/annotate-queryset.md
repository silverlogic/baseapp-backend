# `annotate_queryset` and Metadata Sidecars

Counts, sums, and flags belonging to one block but displayed on another block's objects follow a
single uniform pattern in this repo. Learn it once and all six existing implementations read the
same.

## The shape

```text
Target model (Profile, Page, Comment, …)
        │  has a DocumentId
        ▼
DocumentId ──1:1── <Thing>ableMetadata     denormalized counters, maintained on write
                          │
                          ▼
                  annotate_queryset()      correlated Subquery, read path
                          │
                          ▼
              <Thing>ableMetadataService   getters prefer annotation, fall back to a query
                          │
                          ▼
                 <Thing>sInterface         GraphQL fields
```

Six implementations to copy from:

| Metadata model | File:line | Annotations produced |
|---|---|---|
| `AbstractCommentableMetadata` | `baseapp_comments/models.py:207` | `_commentable_comments_count`, `_commentable_is_comments_enabled`, `replies_count_total` |
| `AbstractReactableMetadata` | `baseapp_reactions/models.py:163` | `_reactable_reactions_count`, `_reactable_is_reactions_enabled`, `reactions_count_total` |
| `AbstractFollowableMetadata` | `baseapp_follows/models.py:33` | `_followable_followers_count`, `_followable_following_count` |
| `AbstractBlockableMetadata` | `baseapp_blocks/models.py:116` | `_blockable_blockers_count`, `_blockable_blocking_count` |
| `AbstractRatableMetadata` | `baseapp_ratings/models.py:129` | `_ratable_ratings_count`, `_ratable_ratings_sum`, `_ratable_ratings_average`, `_ratable_is_ratings_enabled` |
| `AbstractReportableMetadata` | `baseapp_reports/models.py:164` | `_reportable_reports_count` |

## Step 1 — the annotation classmethod

`baseapp_comments/models.py:207` is the canonical form:

```python
    @classmethod
    def annotate_queryset(cls, queryset) -> models.QuerySet:
        """
        Annotate a queryset with commentable metadata to prevent N+1 queries.
        Adds _commentable_comments_count and _commentable_is_comments_enabled.
        For Comment querysets only, also adds replies_count_total (CommentFilter / ordering).
        Resolves the model ContentType id once per call (Django's ContentType manager caches
        until ContentType.objects.clear_cache()).
        """
        model_cls = queryset.model
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        metadata_qs = cls.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        annotations = {
            "_commentable_comments_count": Subquery(metadata_qs.values("comments_count")[:1]),
            "_commentable_is_comments_enabled": Subquery(
                metadata_qs.values("is_comments_enabled")[:1],
                output_field=models.BooleanField(),
            ),
        }
        ...
        return queryset.annotate(**annotations)
```

Rules encoded there:

- **Derive everything from `queryset.model`.** The same method annotates `Profile`, `Page`, and
  `Comment` querysets.
- **Resolve the ContentType once per call**, outside the subquery. Django's manager caches it.
- **`OuterRef("pk")` + `.values(...)[:1]`** — one correlated subquery per annotation, inlined into
  the parent SELECT. No extra round-trip.
- **Private names get a `_<thing>able_` prefix.** Public names (no underscore) are the ones clients
  may filter and order by — see step 4.

## Step 2 — `Coalesce` so a missing row is free

A target with no metadata row must cost zero extra queries and return a sane default.
`baseapp_reactions/models.py:163` shows both the coalesce and the JSON-key flattening:

```python
        total_subq = Subquery(
            metadata_qs.annotate(total=KeyTextTransform("total", "reactions_count")).values(
                "total"
            )[:1]
        )
        return queryset.annotate(
            _reactable_reactions_count=Subquery(metadata_qs.values("reactions_count")[:1]),
            _reactable_is_reactions_enabled=Coalesce(
                Subquery(
                    metadata_qs.values("is_reactions_enabled")[:1],
                    output_field=models.BooleanField(),
                ),
                Value(True),
            ),
            reactions_count_total=Coalesce(
                Cast(total_subq, output_field=IntegerField()),
                Value(0),
            ),
        )
```

`KeyTextTransform` + `Cast` flattens a JSON key into a real integer expression so `ORDER BY` works
on it. A `JSONField` count dict cannot be sorted on directly.

## Step 3 — the service façade and the read-through contract

This is what makes annotating *optional*. `baseapp_follows/services.py:43`:

```python
    def get_followers_count(self, obj) -> int:
        """Return followers count for `obj`. Uses annotation if available."""
        if hasattr(obj, "_followable_followers_count"):
            val = obj._followable_followers_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.followers_count if metadata else 0

    def annotate_queryset(self, queryset) -> models.QuerySet:
        return FollowableMetadata.annotate_queryset(queryset)
```

The `hasattr` check is the whole contract: annotate and the resolver is free; don't annotate and it
still returns the right answer, one query per object. Correctness never depends on the
optimization — only performance does. Keep it that way, and always handle `val is None` (an
annotation with no matching row is `None`, not `0`).

## Step 4 — apply it

Give the metadata model a `get_annotations(model_cls)` classmethod returning the expressions keyed
by alias (`annotate_queryset` is then `queryset.annotate(**cls.get_annotations(queryset.model))`),
and expose it on the service. Apply it in order of preference:

```python
# 1. field-level optimizer hint — annotated only when the field is selected.
#    Preferred for shared-interface fields; see optimizer-hooks.md.
def _metadata_annotation(name: str) -> dict:
    def annotation(info: Info) -> Any:
        service = shared_services.get("commentable_metadata")
        return service.get_annotations(model_from_info(info))[name]

    return {name: annotation}


@strawberry_django.field(annotate=_metadata_annotation("_commentable_comments_count"))
def comments_count(self, info: Info) -> CommentsCount: ...

# 2. get_queryset — when the annotation is needed regardless of selection
@classmethod
def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
    if service := shared_services.get("reactable_metadata"):
        queryset = service.annotate_queryset(queryset)
    return queryset
```

Public annotations become filterable and orderable. The FilterSet runs *after* the optimizer, so a
FilterSet that orders by an annotation adds it itself, only when asked
(`baseapp_comments/strawberry/filters.py`):

```python
_ORDERING_ANNOTATIONS = {
    "replies_count_total": "commentable_metadata",
    "reactions_count_total": "reactable_metadata",
}


class CommentFilter(django_filters.FilterSet):
    order_by = django_filters.OrderingFilter(
        fields=(
            ("created", "created"),
            *apply_if_installed(
                "baseapp_reactions", [("reactions_count_total", "reactions_count_total")]
            ),
            ("replies_count_total", "replies_count_total"),
        )
    )

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        ordering = self.form.cleaned_data.get("order_by") or []
        for alias in {value.lstrip("-") for value in ordering} & _ORDERING_ANNOTATIONS.keys():
            service = shared_services.get(_ORDERING_ANNOTATIONS[alias])
            if service and alias not in queryset.query.annotations:
                queryset = queryset.annotate(
                    **{alias: service.get_annotations(queryset.model)[alias]}
                )
        return super().filter_queryset(queryset)
```

Keep the alias → service map next to the ordering fields — a filter referencing an annotation that
some other file must supply is exactly the coupling that breaks silently.

## Maintaining the counter on the write path

| Style | Use when | Example |
|---|---|---|
| Atomic `F() + 1` / `F() - 1` UPDATE | A single row changes. O(1), lock-free. **Preferred.** | `baseapp_follows` — see its README; reconciliation via `recount_followers_count` offline |
| Single `GROUP BY` recompute | The count is a dict keyed by type | `baseapp_reactions/models.py:123`, `baseapp_reports/models.py:105` |

```python
        rows = (
            ReactionModel.objects.filter(target_document_id=metadata.target_id)
            .values("reaction_type")
            .annotate(n=Count("id"))
        )
```

Never `COUNT(*)` the whole relation on every save, and never take `SELECT FOR UPDATE` on the live
path — `baseapp_follows/tests/test_follow_count.py:117` asserts against both by inspecting the
captured SQL.

## When to annotate live instead

Not everything needs a sidecar. A live correlated subquery is fine when the count is cheap and
rarely hot — `baseapp_mentions/services.py:169` builds one from scratch rather than denormalizing:

```python
        count_qs = (
            Mention.objects.filter(
                target_document__content_type_id=ct_id,
                target_document__object_id=OuterRef("pk"),
            )
            .order_by()
            .values("target_document")
            .annotate(c=Count("id"))
            .values("c")
        )
        return Coalesce(Subquery(count_qs[:1]), Value(0))
```

The `.order_by()` reset matters: a model `Meta.ordering` leaks into the subquery's `GROUP BY` and
breaks the aggregate.

## Anti-patterns

- A `@property` that queries the database. Not filterable, not orderable, N+1 across any list.
  Annotate instead.
- Omitting `Coalesce` — every target without a metadata row returns `None`, and resolvers start
  guarding with extra queries.
- Sorting on a raw `JSONField` count. Flatten with `KeyTextTransform` + `Cast` into a public
  annotation first.
- Resolving the ContentType inside the subquery, or once per row.
- A getter that reads the annotation but has no fallback — correctness then depends on every call
  site remembering to annotate.
- Recomputing a count with `COUNT(*)` on every save when an `F()` increment would do.
- Forgetting `.order_by()` on an aggregate subquery when the model has `Meta.ordering`.
