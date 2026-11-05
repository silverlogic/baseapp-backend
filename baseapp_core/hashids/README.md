# Baseapp Core - HashIds

HashIds provides a set of abstractions and helper functions designed to help models across the system avoid exposing sequential integer primary keys to external services, such as frontend applications. Compared to sequential PKs, public IDs make it significantly harder to infer other records, which is generally a safer and more appropriate approach than exposing raw database primary keys.

To omit internal PKs, models must be made compatible with HashIds, and the appropriate abstractions must be used when defining queries, mutations, or subscriptions in Graphene, as well as when creating new endpoints in DRF.


## Making Your Apps Compatible With HashIds

### Making model compatible with hashIds

This is fairly simple. We use the DocumentId pattern (see [Baseapp Core](../README.md#documentid-model) for more details). You just need to ensure that any model that should omit its internal integer primary key extends the `baseapp_core.models.DocumentIdMixin` abstraction.

### Making Graphene ObjectTypes compatible with hashIds

This is also very simple. You just need implement the `baseapp_core.graphql.DjangoObjectType` abstraction and include the `baseapp_core.graphql.Node` interface in the ObjectType interfaces.

```python
from baseapp_core.graphql import DjangoObjectType, Node as RelayNode
from baseapp_chats.graphql.interfaces import ChatRoomsInterface

class ProfileObjectType(DjangoObjectType):
    class Meta:
        interfaces = (RelayNode, ChatRoomsInterface)
```

### Making DRF endpoints compatible with HashIds

Every piece below falls back to plain primary keys for a model without `DocumentIdMixin`, or when `ENABLE_PUBLIC_ID_LOGIC = False`, so it is safe to use on any model.

#### Lookups: `PublicIdLookupMixin`

Make your ViewSets extend `baseapp_core.rest_framework.mixins.PublicIdLookupMixin`. It overrides `get_object` so that the URL id is resolved as a public id instead of the internal primary key, with the view's queryset filters and object permissions still applied.

```python
from baseapp_core.rest_framework.mixins import PublicIdLookupMixin

class PostViewSet(PublicIdLookupMixin, viewsets.ModelViewSet):
    ...
```

- A public id of another model, or one that maps to nothing, answers 404.
- The integer pk is still accepted while `allow_pk_lookup` is true. Set it on the ViewSet, or project-wide with `BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP` (default `True`). When it is false, `/posts/12/` answers 404 for a model that uses public ids.
- `lookup_value_regex` defaults to `PUBLIC_ID_LOOKUP_REGEX` (an integer or a UUID4), so the router emits one detail pattern for both. A ViewSet that looks up by something else (a slug, a non-UUID4 key) sets its own `lookup_value_regex`.
- `filter_queryset` annotates `mapped_public_id`, so rendering `public_id` in a list costs no query per row, even when the ViewSet overrides `get_queryset`. Set `annotate_mapped_public_id = False` to skip it. `get_queryset()` itself is not annotated: a custom action that serializes `self.get_queryset()` directly should pass it through `self.filter_queryset()` or `annotate_public_ids()`.

#### Serializers: `PublicIdField` and `PublicIdRelatedField`

`baseapp_core.rest_framework.fields` has two fields:

- `PublicIdField()`: read-only, renders the object's public id (`source="*"` by default). Use it for `id` in plain `Serializer`s, or with `source="<relation>"` for a related object.
- `PublicIdRelatedField(queryset=...)`: a `PrimaryKeyRelatedField` that renders and accepts public ids. A public id of another model is a validation error. An integer pk is accepted while `allow_pk_lookup` is true (field argument, default `BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP`). It supports `many=True`.

```python
from baseapp_core.rest_framework.fields import PublicIdField, PublicIdRelatedField

class PostSerializer(serializers.Serializer):
    id = PublicIdField()
    author = PublicIdRelatedField(queryset=User.objects.all())
    tags = PublicIdRelatedField(queryset=Tag.objects.all(), many=True)
```

`baseapp_core.rest_framework.serializers.ModelSerializer` already renders the model's own `id` as its public id. With `BASEAPP_REST_PUBLIC_ID_RELATED_FIELDS = True` (default `False`, because it changes the output of existing endpoints) it also maps foreign keys and many-to-many fields to models that use public ids onto `PublicIdRelatedField`. Every such field then reads the related object's public id, which costs one query per related object unless the queryset loads it (see [Avoiding a query per row](#avoiding-a-query-per-row-annotate_public_ids)), so annotate or prefetch the list querysets before turning the setting on.

#### Filters: `PublicIdFilter` and `PublicIdMultipleFilter`

`baseapp_core.rest_framework.filters` has two django-filter filters that take public ids and filter on the matching pk:

```python
from baseapp_core.rest_framework.filters import PublicIdFilter, PublicIdMultipleFilter

class PostFilterSet(django_filters.FilterSet):
    author = PublicIdFilter()                                  # ?author=<id>
    authors = PublicIdMultipleFilter(field_name="author")      # ?authors=<id>&authors=<id> or ?authors=<id>,<id>
    tag = PublicIdFilter(field_name="tags", model=Tag, distinct=True)
```

The model is inferred from `field_name` on the FilterSet's model, or given with `model=`. An id of another model, a malformed value, or an integer pk while pk lookups are disallowed, is a 400. A public id that maps to no row matches nothing (an empty list), the same answer as an existing id outside the queryset, so the filter does not tell whether an id exists. Both take `allow_pk_lookup=`.

#### Avoiding a query per row: `annotate_public_ids`

Reading `public_id` without help costs one DocumentId query per object, and per related object. Load the ids with the queryset instead:

```python
from baseapp_core.hashids.strategies import annotate_public_ids

def get_queryset(self):
    queryset = Post.objects.select_related("author")
    return annotate_public_ids(queryset, "author", "thread__owner")
```

- The queryset's own rows get `mapped_public_id` (pass `include_self=False` to skip), which `public_id` reads.
- Each path gets `<path>_public_id` (`author_public_id`, `thread__owner_public_id`), which `PublicIdRelatedField` reads for the matching `source`. Paths must follow foreign keys or one-to-one fields.
- Each relation on a path also gets `<prefix>_public_id_pk` (`author_public_id_pk`, `thread_public_id_pk`, `thread__owner_public_id_pk`): its key when the row was loaded. `PublicIdRelatedField` reads the public id through `get_annotated_public_id(instance, path)`, which returns `None` once a relation on the path has been reassigned on the instance, so the response to an update renders the new related id rather than the annotated one.
- For many-to-many and reverse relations, prefetch the documents instead: `prefetch_related("tags__document")`. `public_id` reads a prefetched `document` relation without a query.

Lower level, `PublicIdQuerysetAnnotatorStrategy.get_annotations(model_cls, field="pk", alias="mapped_public_id")` returns the annotation for any pk path and alias.

#### Resolving ids by hand

`drf_get_pk_from_public_id_or_pk(value, model_cls, allow_pk_lookup=None)` in `baseapp_core.hashids.strategies` returns the pk to look a `model_cls` row up by, or `None` when the value cannot be one of its ids (unknown, another model's public id, or a pk while pk lookups are disallowed). `drf_get_pk_from_public_id_using_strategy(value, expected_model=...)` is the lower-level call: it returns `None` for an unknown public id and raises `DRFResolverStrategy.NoInstanceFound` for another model's. `Model.get_by_public_id(public_id)` returns `None` for another model's public id.

#### Settings

| Setting | Default | Effect |
|---|---|---|
| `BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP` | `True` | REST lookups, `PublicIdRelatedField` and the filters accept integer pks of models that use public ids. Turn it off once clients only send public ids. |
| `BASEAPP_REST_PUBLIC_ID_RELATED_FIELDS` | `False` | `ModelSerializer` renders and accepts foreign keys and many-to-many fields as public ids. |


## Maintaining the HashIds Feature

All HashIds heuristics and logic are centralized in the `baseapp_core/hashids/` folder. The idea is that anything requiring HashIds resolution or access should rely on the functions provided there. This helps maximize reuse, reduce redundancy, and keep the behavior consistent across the system. Another important requirement is backward compatibility with older versions of Baseapp. The HashIds feature should be fully optional, meaning it must be possible to disable it and have the system continue to work using primary keys as filters (Legacy Mode).

Below is a set of practices and patterns to keep in mind when maintaining this feature.

### The Strategy pattern

The public ID resolver is implemented using the Strategy design pattern. This pattern was chosen to support enabling or disabling the HashIds feature on a per project basis. It also accounts for the fact that some models may not be compatible with HashIds, for example because they do not extend the `DocumentIdMixin` class.

Inside the `baseapp_core/hashids/strategies/` folder, the structure looks like this:

```
baseapp_core/hashids/strategies
├── __init__.py
├── bundle.py
├── interfaces/
├── legacy/
├── pk/
└── public_id/
```

The key idea behind this structure is that each folder represents a different strategy implementation. All strategies implement the interfaces defined in the `interfaces/` folder, and the `__init__.py` file contains the heuristics that decide which strategy should be used at runtime.

#### Legacy vs Public Id

The Legacy strategy follows the default behavior of Django, DRF, and Graphene. It relies on model primary keys to handle queries and updates coming from external services. If you decide to keep using primary keys in the frontend, which is not recommended, you can disable the Public Id strategy with the Django setting `ENABLE_PUBLIC_ID_LOGIC = False`. When disabled, the system will rely exclusively on the Legacy strategy.

The Public Id strategy uses the `public_id` field from the `DocumentId` model. This strategy is responsible for resolving and exposing public IDs and is the recommended approach.

#### __init__.py in detail

The `__init__.py` file contains the heuristics for selecting the appropriate strategy, as well as the public functions that other parts of the system can use to resolve public IDs for external service workflows.

Some of these public functions are straightforward, such as `get_hashids_strategy_from_instance_or_cls`, which selects the appropriate strategy based on a model instance or class. Others are more complex and exist to support advanced use cases. Graphene is a good example, where multiple helper functions with different inputs and outputs are required to fully replace the default `global_id` pattern, which remains available through the Legacy strategy.

For now, public facing functions should continue to live in this module. If a more organized structure becomes necessary, a proposal should be made to the CoP members.

Public facing functions here are functions that other parts of the system are expected to use when resolving or working with public IDs.

#### Strategy selection heuristics

Currently, the heuristics for selecting the Public Id strategy over the Legacy one are:

1. The Public Id strategy must be enabled with the Django setting `ENABLE_PUBLIC_ID_LOGIC` (`True` by default).
2. The model being filtered must extend `DocumentIdMixin`.
3. The model being filtered must use an auto incrementing primary key.

### Optimization

Optimization is a critical aspect of the HashIds feature. When using the Public Id strategy, care must be taken to avoid introducing extra queries for each model instance when accessing `public_id`, since `DocumentId` is linked through a generic foreign key.

This issue becomes more evident in GraphQL edge and node queries that involve large objects with deeply nested object types and large result sets. To address this, we introduced the `baseapp_core.graphql.DjangoObjectType` abstraction. By leveraging the `query_optimizer` package for Graphene, we dynamically annotate the resolution of these generic foreign keys based on the GraphQL query structure before executing the queryset. This approach prevents query explosions.

While the Public Id strategy still results in more queries than the Legacy mode, the overhead is now acceptable.

DRF has no query optimizer, so DRF endpoints load public ids explicitly with `annotate_public_ids` and `prefetch_related("<relation>__document")` (see [Avoiding a query per row](#avoiding-a-query-per-row-annotate_public_ids)). `PublicIdLookupMixin` annotates the ViewSet's own rows.

Whenever making structural changes to Baseapp HashIds or GraphQL-related code, make sure to validate the impact on query performance.
