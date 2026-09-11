# Field-Level `optimizer_hook`

`pre_optimization_hook` optimizes *a type*. `optimizer_hook` optimizes *a field* — and the
compiler calls it only when that field is actually selected.

Reach for it when a field lives on a **shared GraphQL interface**. An interface is mixed into many
ObjectTypes across many blocks; requiring each of them to add the right lines to its own
`pre_optimization_hook` is both a coupling problem and a reliability problem. Attaching the
optimization to the field means consumers wire up nothing.

## When to use which

| Situation | Mechanism |
|---|---|
| Column/relation this specific type always needs | `pre_optimization_hook` |
| Field on a shared interface, consumed by other blocks' types | `optimizer_hook` |
| Expensive annotation only some queries want | `optimizer_hook` — pay per selection |
| Relation with no direct FK, reached through `DocumentId` | `optimizer_hook` (only way to register the prefetch path) |

## Wiring

Attach the function to the field object as an attribute after declaring the field.
`baseapp_mentions/graphql/interfaces.py:28`:

```python
# The `*_optimizer_hook` functions below are attached to each field's
# `optimizer_hook` attribute. The query optimizer calls them during AST
# compilation only when the matching field is selected in the GraphQL
# query, so the extra annotation or prefetch the resolver needs is added
# on demand — never paid for on queries that don't touch the field, and
# without requiring every consuming ObjectType to wire it up in its own
# `pre_optimization_hook`.


def _mentions_count_optimizer_hook(compiler) -> None:
    """Attach `_mentions_count` on the parent optimizer only when
    `mentionsCount` is selected.
    """
    if service := shared_services.get("mentionable_metadata"):
        service.annotate_mentions_count_in_optimizer_compiler(compiler)


class MentionsInterface(RelayNode):
    mentions = DjangoConnectionField(get_object_type_for_model(Mention))
    mentions_count = graphene.Field(graphene.Int)
    is_mentioning_profile = graphene.Field(graphene.Boolean, profile_id=graphene.ID(required=True))

    mentions.optimizer_hook = _mentions_optimizer_hook
    mentions_count.optimizer_hook = _mentions_count_optimizer_hook
    is_mentioning_profile.optimizer_hook = _is_mentioning_profile_optimizer_hook
```

The hook takes the **compiler**, not a queryset. `compiler.optimizer` is the parent optimizer —
the one for the type the interface is mixed into.

## Pattern A — conditional annotation

`baseapp_blocks/services.py:220`:

```python
    def annotate_blockers_count_in_optimizer_compiler(self, compiler: OptimizationCompiler) -> None:
        """Attach `_blockable_blockers_count` to the parent optimizer's annotations.

        Wired from `BlocksInterface.blockers_count.optimizer_hook` so the
        subquery only fires when the GraphQL query actually selects
        `blockersCount`. Setting the annotation on `optimizer.annotations` also
        triggers `query_optimizer`'s auto-promotion of `select_related` to
        `prefetch_related` for nested FK paths (e.g. `block.target`), which is
        what carries the annotation through to the nested Profile load.
        """
        parent = compiler.optimizer
        if parent is None or parent.model is None:
            return
        parent.annotations.setdefault(
            "_blockable_blockers_count", self._blockers_count_subquery(parent.model)
        )
```

The shape to copy:

1. Guard `compiler.optimizer is None or .model is None` and return quietly.
2. Build the subquery from `parent.model` — the hook is generic across every consuming type.
3. `setdefault`, not assignment, so a consumer that already annotated wins.

Same pattern for `blocking_count` at `baseapp_blocks/services.py:237`, and for mentions at
`baseapp_mentions/services.py:208` and `:222`.

## Pattern B — prefetching a virtual relation

The hardest case. `mentions` is a connection on any commentable/postable object, but there is no
FK from the consumer to `Mention` — the link runs through `DocumentId`. Without a hint the
optimizer treats the field as opaque and falls back to a per-parent fetch.

The fix is to register a child `QueryOptimizer` on the `document__<reverse>` path, which promotes
the field to a real `prefetch_related`. `baseapp_mentions/services.py:238`:

```python
    def prefetch_mentions_in_optimizer_compiler(self, compiler: OptimizationCompiler) -> None:
        parent_optimizer = compiler.optimizer
        if parent_optimizer is None or parent_optimizer.model is None:
            return

        Mention = swapper.load_model("baseapp_mentions", "Mention")

        prefetch_path = Mention.document_prefetch_path()
        if prefetch_path in parent_optimizer.prefetch_related:
            return

        mentions_opt = QueryOptimizer(
            model=Mention,
            info=compiler.info,
            name=prefetch_path,
            parent=parent_optimizer,
        )

        # `recursive_set_annotations` in `BaseAppDjangoObjectType.pre_optimization_hook`
        # gates annotation attachment on `"id" in only_fields`; without this, the
        # Profile prefetch below would NOT receive its `mapped_public_id` annotation
        # and the relay-id resolver would fall back to a per-row `DocumentId` lookup.
        mentions_opt.only_fields.append("id")
        mentions_opt.related_fields.extend(["target_document_id", "profile_id"])

        profile_opt = QueryOptimizer(
            model=Profile,
            info=compiler.info,
            name="profile",
            parent=mentions_opt,
        )
        # Same gate: "id" in only_fields ⇒ Profile gets its `mapped_public_id`
        # subquery annotated, killing the per-row DocumentId lookup on relay-id.
        profile_opt.only_fields.append("id")
```

Three non-obvious requirements:

- **Append `"id"` to `only_fields` at every level you construct.** The base hook's annotation
  walker is gated on it (see `query-optimization.md`). Forget it and that level loses its relay-id
  annotation — a silent per-row lookup.
- **Idempotency.** Check `if prefetch_path in parent_optimizer.prefetch_related: return`. Hooks can
  fire more than once per compile.
- **The consuming model must expose `document = GenericRelation(DocumentId)`** so the reverse path
  is a real Django prefetch path. `DocumentIdMixin` declares it, so any consumer inheriting the
  mixin gets it free.

## The interface `Meta.model` requirement

For the AST walker to descend into an inline fragment (`... on BlocksInterface { … }`), the
interface must declare the model it is mixed into. `baseapp_blocks/graphql/object_types.py:49`
records why:

```python
class BlocksInterface(RelayNode):
    ...
    class Meta:
        # `query_optimizer`'s AST walker skips `... on <Interface>` inline
        # fragments whose declared model doesn't match the queryset's model.
        # Pinning Profile here lets the top-level `node(id: profile-relay-id)`
        # optimization pass descend into BlocksInterface's fields when resolving
        # a Profile. Without this, `block.target.blockersCount` never gets its
        # annotation attached on the outer pass and falls back to a per-row
        # `BlockableMetadata` fetch.
        model = Profile
```

`baseapp_core/graphql/relay.py:43` copies this onto `_meta.model` specifically so
`query_optimizer.GraphQLASTWalker` can resolve `fragment_model` from interfaces. Omit it and the
walker skips the fragment — every field inside it goes unoptimized.

## Documenting the contract

Interfaces that carry their own optimization should say so, so consumers don't duplicate it.
`MentionsInterface`'s docstring is the model to follow:

> All optimizer wiring lives on the fields below — consumers do not need to add anything to their
> own `pre_optimization_hook`.

## Anti-patterns

- Forgetting `only_fields.append("id")` on a hand-built `QueryOptimizer`. The most common cause of
  "I added the prefetch and the count barely moved".
- Assigning instead of `setdefault` on `parent.annotations` — clobbers a consumer's own annotation.
- Building the subquery from a hardcoded model instead of `parent.model`. The hook runs for every
  consuming type.
- Omitting `Meta.model` on an interface, then wondering why the hook never fires.
- No `None` guard on `compiler.optimizer` — the hook also runs on non-optimized paths.
- Putting interface optimization into each consuming block's `pre_optimization_hook`. It reverses
  the dependency direction the plugin architecture exists to prevent.
