# The DocumentId Layer

Blocks never foreign-key into each other's tables. A direct FK means removing a block breaks
another block's migrations, and it forces every "commentable" or "ratable" model to be known in
advance.

`DocumentId` is a central registry giving any object a stable identity that other blocks can point
at:

```python
class DocumentId(TimeStampedModel):   # baseapp_core/models.py:60
    public_id = ...        # uuid, also the relay id source
    content_type = ...     # FK to ContentType
    object_id = ...
```

Blocks attach to it, never to each other. Remove a block and you remove its tables; no other
block's schema references them.

## The three mixins

| Mixin | Line | Meaning | Use on |
|---|---|---|---|
| `DocumentIdMixin` | `baseapp_core/models.py:140` | "I can be pointed at" | Any model other blocks may attach to — `Profile`, `Page`, `Comment` |
| `DocumentIdTargetMixin` | `:229` | "I point at a document" (many-to-one) | `Comment`, `Rate`, `Follow`, `Mention` |
| `DocumentIdUniqueTargetMixin` | `:184` | "I am the 1:1 sidecar for a document" | `*ableMetadata` counter tables |

### `DocumentIdMixin`

Makes a model documentable. Adds a `GenericRelation` named `document`, a `public_id` property, and
`get_by_public_id()`. A pgtrigger creates the `DocumentId` row on insert — no signal, no race.

```python
from baseapp_core.models import DocumentIdMixin


class Page(DocumentIdMixin, models.Model):
    ...
```

The `document` GenericRelation is not cosmetic: it is the prefetch path virtual-relation
optimization walks (`document__<reverse>`, see `optimizer-hooks.md`). A model without it cannot
have its mentions/comments batched.

Fallback when a trigger isn't available: `DocumentId.get_or_create_for_object(instance)`.

### `DocumentIdTargetMixin`

A non-unique FK plus a transparent `target` property:

```python
target_document = models.ForeignKey(
    DocumentId, related_name="%(app_label)s_%(class)s", ...
)
```

Reading `obj.target` gives the concrete object back. On a list path resolve it through the
request-scoped cache rather than the raw property — `baseapp_core/graphql/utils.py:73`:

```python
    def resolve_target(root, info, **kwargs) -> models.Model | None:
        if not root.target_document_id:
            return None
        return resolve_document_content_object(
            root.target_document, info, cache_attr="_comment_target_cache"
        )
```

`resolve_document_content_object` collapses repeated `(content_type_id, object_id)` lookups within
one request into a single fetch, and returns the prefetched instance for free when the parent used
`GenericPrefetch`. **Always use it in a resolver instead of touching `.content_object` directly.**
This repo has no dataloaders; this cache plus optimizer prefetching fills that role.

### `DocumentIdUniqueTargetMixin`

For sidecar tables — one row per document, PK'd on the document:

```python
class FooableMetadata(DocumentIdUniqueTargetMixin, models.Model):
    foos_count = models.PositiveIntegerField(default=0)
    is_foos_enabled = models.BooleanField(default=True)
```

Supplies `get_for_object(obj)` and `get_or_create_for_object(obj)`. This is the storage half of the
counter pattern in `annotate-queryset.md`.

## Choosing

- Other blocks may attach things to my model → `DocumentIdMixin`.
- My model attaches to arbitrary objects → `DocumentIdTargetMixin`.
- My model holds per-target counters/flags → `DocumentIdUniqueTargetMixin` + `annotate_queryset`.

A block frequently uses two: `Comment` is both a target (it comments *on* something) and
documentable (you can comment *on* a comment).

## Why this makes optimization possible

`DocumentId` also carries `public_id`, the relay id source. That is what lets the base
`pre_optimization_hook` inline a single `mapped_public_id` subquery instead of one lookup per row
(`query-optimization.md`). Adopting the mixins is what puts a block on the optimized path.

## Migrating a legacy GenericForeignKey

Blocks that predate this layer ship helpers under `migration_helpers/` — see
`baseapp_comments/migration_helpers/convert_comments_gfk_into_document_id_helper.py` and the
matching `tests/test_migration_helper_*.py`. Follow that shape rather than hand-writing a data
migration, and use `get_apps_model` (see `swappable-models.md`) inside it.

## Anti-patterns

- A `ForeignKey` or `GenericForeignKey` from one block to another block's model. Route through
  `DocumentId`.
- Accessing `document.content_object` directly in a resolver instead of
  `resolve_document_content_object`.
- Adding `DocumentIdTargetMixin` to a model other blocks need to attach *to*. That is
  `DocumentIdMixin`; they are different directions.
- Omitting `DocumentIdMixin` on a model that should support mentions/comments — the
  `document__<reverse>` prefetch path won't exist and the optimizer falls back to per-row fetches.
- Counter columns on the target model itself instead of a sidecar. Couples the schema and forces a
  migration on every consuming project.
