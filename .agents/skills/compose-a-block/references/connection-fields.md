# Connection Fields

Which connection-field class you pick decides whether **any** of the optimization in
`query-optimization.md`, `optimizer-hooks.md`, and `annotate-queryset.md` runs at all.

## The choice that matters

| Class | Optimizer runs? |
|---|---|
| `query_optimizer.DjangoConnectionField` | **Yes.** `pre_optimization_hook` and every field `optimizer_hook` fire. |
| `graphene_django.filter.DjangoFilterConnectionField` | **No.** The compiler never runs; your hooks are dead code. |

```python
from query_optimizer import DjangoConnectionField        # optimized
from graphene_django.filter import DjangoFilterConnectionField   # NOT optimized
```

**Default to `query_optimizer.DjangoConnectionField` for new fields.**

This repo is mid-migration and roughly half the connection fields are still the unoptimized class,
so **you cannot infer the right choice from neighbouring code**. Currently on the optimized class:
`baseapp_chats`, `baseapp_comments`, `baseapp_blocks`, `baseapp_follows`, `baseapp_mentions`,
`baseapp_ratings`. Still on the unoptimized one: `baseapp_profiles`, `baseapp_reactions`,
`baseapp_reports`, `baseapp/content_feed`, `baseapp/activity_log`, and most root
`graphql/queries.py` fields.

`baseapp_profiles` is the sharpest example of the mismatch: it has a real
`pre_optimization_hook` (`baseapp_profiles/graphql/object_types.py:205`) documented as the way to
avoid N+1 on `followersCount`, but `ProfilesInterface.profiles`, `members`, and root
`all_profiles` are all `DjangoFilterConnectionField` — so on those paths the hook never executes.

The chats regression suite treats a silent revert as the top suspect when a count jumps
(`baseapp_chats/tests/test_graphql_query_counts.py`):

> Likely causes (in priority order):
>   - `chatRoom.allMessages` reverted to `DjangoFilterConnectionField`

### Filtering still works

The optimized class is not a downgrade. Declare `filterset_class` on the ObjectType's `Meta` as
usual; `DjangoConnectionField` honours it. There is no need to reach for
`DjangoFilterConnectionField` to get filtering.

```python
class BaseCommentObjectType:
    class Meta:
        model = Comment
        filterset_class = CommentFilter
```

### Changing an existing field

Switching a field to `query_optimizer.DjangoConnectionField` activates hooks that were previously
inert. That is the point, but it changes SQL. Pin the count with a test *before* the switch and
compare after — see `query-count-tests.md`.

## `CountedConnection`

Every ObjectType gets `total_count` and `edge_count` for free.
`baseapp_core/graphql/object_types.py:24` assigns it automatically in
`__init_subclass_with_meta__`, so do not set `connection_class` yourself unless you are replacing
it deliberately.

```python
class CountedConnection(graphene.Connection):
    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(self, info, **kwargs) -> int:
        return self.length

    def resolve_edge_count(self, info, **kwargs) -> int:
        return len(self.edges)
```

Neither costs an extra query beyond the optimizer's own count subquery.

The same method also names the type after the model, which is why ObjectTypes don't declare
`name` — `CommentObjectType` surfaces as `Comment`.

## Return the queryset, never a list

Resolvers must return an unevaluated queryset. The connection field applies optimization *and*
pagination; hand it a list and you lose both, and slicing happens in Python after loading every
row.

```python
        # Return the un-evaluated queryset so the DjangoConnectionField handles both
        # optimization and pagination (first/after slicing).
        return qs
```

For the same reason, never call `optimize()` eagerly in a resolver — it evaluates the queryset and
breaks pagination.

Order by a stable field. Cursor pagination needs deterministic ordering or pages duplicate and drop
rows.

## Escape hatch: `skip_ast_walker`

`baseapp_core/graphql/optimizer.py:270`:

```python
def skip_ast_walker(qs: QuerySet) -> QuerySet:
    """
    Mark a queryset as optimized to explicitly bypass the query_optimizer AST walker.

    This function should be used when optimization should be skipped entirely, for example:
      - When returning an empty queryset, such as with `model_class.objects.none()`.
      - In the context of nested connections of the same type in Graphene
        (e.g., comments -> comments), where query_optimizer AST-based optimization
        is incompatible or produces incorrect results.
    """
    mark_optimized(qs)
    return qs
```

Use it on every early-return empty queryset:

```python
        if service and not service.is_comments_enabled(root):
            return skip_ast_walker(Comment.objects.none())
```

## Nested same-type connections

A connection of type `X` nested inside `X` (`comments -> comments`) defeats the AST walker: it
can't work out which field nodes belong to the inner level. `baseapp_core/graphql/optimizer.py`
supplies the workaround — `ConnectionFieldNodeExtractor` recovers the inner field nodes and
`NestedConnectionInfoProxy` fakes the parent type, stashed on the queryset's `_hints` for the
patched compiler to pick up.

`baseapp_comments/graphql/object_types.py:92`:

```python
            # When the root is a comment used as a target, the AST walker can't handle the
            # nested comments -> comments structure with the regular info.  Stash a
            # NestedConnectionInfoProxy on the queryset hints so the patched
            # OptimizationCompilerPatch (in baseapp_core.graphql.optimizer) picks it up
            # when the DjangoConnectionField compiles the optimisation.  This avoids calling
            # optimize() eagerly, which would evaluate the queryset and break pagination.
            queryset_field_nodes = ConnectionFieldNodeExtractor(info).get_sliced_field_nodes()
            info_proxy = NestedConnectionInfoProxy(info, queryset_field_nodes=queryset_field_nodes)
            qs._hints[NESTED_INFO_PROXY_HINT] = info_proxy
```

This is deep infrastructure. If you need it, copy the comments implementation exactly and add a
query-count test; do not improvise.

## Anti-patterns

- Reaching for `DjangoFilterConnectionField` to get filtering. `DjangoConnectionField` filters too,
  and keeps the optimizer.
- Copying the connection-field import from a neighbouring block. Half of them are the unoptimized
  class.
- Returning `.objects.none()` without `skip_ast_walker`.
- Returning a list, or calling `.all()` to "materialize" before returning.
- Calling `optimize()` inside a resolver — evaluates the queryset, breaks pagination.
- Setting `connection_class` by hand and losing `total_count` / `edge_count`.
- A connection with no stable `order_by`.
