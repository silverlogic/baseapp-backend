# BaseApp Ratings

Reusable app that lets users rate any model.

## How to install

```bash
pip install baseapp-backend
```

Add `baseapp_ratings` to `INSTALLED_APPS`. The package registers itself as a plugin
(see `baseapp_ratings.plugin:RatingsPlugin`), so:

- `RatingsQueries` / `RatingsMutations` are contributed via
  `plugin_registry.get_all_graphql_queries()` / `get_all_graphql_mutations()`.
- `RatingsPermissionsBackend` is contributed via
  `plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_ratings")`.
- The `RatingsInterface` GraphQL interface is registered by name; consumers fetch
  it from `graphql_shared_interfaces` instead of importing it directly.
- A `ratable_metadata` shared service exposes
  `get_ratings_count(obj)` / `get_ratings_sum(obj)` / `get_ratings_average(obj)` /
  `is_ratings_enabled(obj)` / `annotate_queryset(qs)` for any object with a
  `DocumentId`. Consumers should use this service instead of inheriting from a mixin.

## How to use

### GraphQL — opt a type into ratings

Request the interface by name in your object type's `Meta.interfaces`:

```python
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class UserNode(DjangoObjectType):
    class Meta:
        interfaces = graphql_shared_interfaces.get(RelayNode, "RatingsInterface")
```

When `baseapp_ratings` is installed the registry returns the real
`RatingsInterface`; when it isn't, the call falls back to defaults so the type
still works.

### GraphQL — exposing the schema

Nothing to do. The plugin entry-point in `pyproject.toml` registers
`RatingsQueries` and `RatingsMutations`, and the project's root `Query` /
`Mutation` should already spread `*plugin_registry.get_all_graphql_queries()`
and `*plugin_registry.get_all_graphql_mutations()`. `rateCreate` and the
`Rate` node show up automatically.

### Reading ratings counts on a model

Counts live on `RatableMetadata` (one row per `DocumentId`), not on the rated
model itself. Read them via the shared service:

```python
from baseapp_core.plugins import shared_services


service = shared_services.get("ratable_metadata")
count = service.get_ratings_count(my_obj)        # int
total = service.get_ratings_sum(my_obj)          # int
average = service.get_ratings_average(my_obj)    # float
enabled = service.is_ratings_enabled(my_obj)     # bool, defaults to True
```

For querysets that will resolve `ratingsCount` for many rows, annotate up front to
avoid N+1:

```python
qs = service.annotate_queryset(qs)
```

The `Rate.save()` / `Rate.delete()` hooks already maintain
`RatableMetadata.ratings_count` / `ratings_sum` / `ratings_average` for you whenever
a rate is added or removed.

## How to customise the Rate model

Define a concrete model in your project that subclasses the abstracts:

```python
# myproject/ratings/models.py
from baseapp_ratings.models import AbstractRate, AbstractRatableMetadata


class Rate(AbstractRate):
    class Meta(AbstractRate.Meta):
        pass


class RatableMetadata(AbstractRatableMetadata):
    class Meta(AbstractRatableMetadata.Meta):
        pass
```

Add the new app to `INSTALLED_APPS`, run `makemigrations` / `migrate`, and point
the swapper settings at it:

```python
# settings.py
BASEAPP_RATINGS_RATE_MODEL = "ratings.Rate"
BASEAPP_RATINGS_RATABLEMETADATA_MODEL = "ratings.RatableMetadata"
```

## Writing test cases in your project

`AbstractRateFactory` helps you build factories for the swapped Rate model:

```python
import factory
from baseapp_ratings.tests.factories import AbstractRateFactory


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "users.User"


class UserRateFactory(AbstractRateFactory):
    target = factory.SubFactory(UserFactory)

    class Meta:
        model = "ratings.Rate"   # or "baseapp_ratings.Rate" if you didn't swap
```

## Migrating an existing project to RatableMetadata

Older projects inherited a `RatableModel` mixin that added `ratings_count`,
`ratings_sum`, `ratings_average`, and `is_ratings_enabled` columns directly on
the rated model. That mixin has been removed. To migrate:

1. Add a migration that creates the `RatableMetadata` table for your project
   (mirror `testproject/ratings/migrations/0002_ratablemetadata.py`).
2. Add a follow-up migration that calls `migrate_legacy_ratings_to_metadata(...)`
   from `baseapp_ratings.migration_helpers.convert_legacy_ratings_count_to_metadata_helper`,
   passing your model's app label and name. After the data is moved,
   `RemoveField` the legacy columns.
3. If you ever need to recompute counts from live `Rate` rows, call
   `seed_ratable_metadata_from_rates(...)` from
   `baseapp_ratings.migration_helpers.seed_ratable_metadata_from_rates_helper`.

## Migrating an existing project to ``target_document``

The `Rate` model previously stored its target via a `GenericForeignKey` over
(`target_content_type`, `target_object_id`). It now stores it as
`target_document = ForeignKey(DocumentId)` for loose coupling. To migrate, use
`migrate_rate_targets_to_document_id` from
`baseapp_ratings.migration_helpers.convert_rates_gfk_into_document_id_helper`.
See `testproject/ratings/migrations/0003_convert_target_to_document.py` for a
complete example: AddField nullable → RunPython backfill → AlterField NOT NULL
→ RemoveField on legacy GFK columns → re-add new index/unique_together.

## How to develop

Clone the monorepo into your backend directory:

```bash
git clone git@github.com:silverlogic/baseapp-backend.git
```

Then install editable:

```bash
pip install -e baseapp-backend
```
