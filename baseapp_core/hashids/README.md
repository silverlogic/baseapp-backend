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

Simply ensure that your ViewSets extend `baseapp_core.rest_framework.mixins.PublicIdLookupMixin`. This mixin overrides the `get_object` method so that lookups are resolved using the public_id instead of the internal primary key.


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

The Legacy strategy follows the default behavior of Django, DRF, and Graphene. It relies on model primary keys to handle queries and updates coming from external services. If you decide to keep using primary keys in the frontend, which is not recommended, you can disable the Public Id strategy through the constance configuration `ENABLE_PUBLIC_ID_LOGIC`. When disabled, the system will rely exclusively on the Legacy strategy.

The Public Id strategy uses the `public_id` field from the `DocumentId` model. This strategy is responsible for resolving and exposing public IDs and is the recommended approach.

#### __init__.py in detail

The `__init__.py` file contains the heuristics for selecting the appropriate strategy, as well as the public functions that other parts of the system can use to resolve public IDs for external service workflows.

Some of these public functions are straightforward, such as `get_hashids_strategy_from_instance_or_cls`, which selects the appropriate strategy based on a model instance or class. Others are more complex and exist to support advanced use cases. Graphene is a good example, where multiple helper functions with different inputs and outputs are required to fully replace the default `global_id` pattern, which remains available through the Legacy strategy.

For now, public facing functions should continue to live in this module. If a more organized structure becomes necessary, a proposal should be made to the CoP members.

Public facing functions here are functions that other parts of the system are expected to use when resolving or working with public IDs.

#### Strategy selection heuristics

Currently, the heuristics for selecting the Public Id strategy over the Legacy one are:

1. The Public Id strategy must be enabled through the constance configuration `ENABLE_PUBLIC_ID_LOGIC`.
2. The model being filtered must extend `DocumentIdMixin`.
3. The model being filtered must use an auto incrementing primary key.

### Optimization

Optimization is a critical aspect of the HashIds feature. When using the Public Id strategy, care must be taken to avoid introducing extra queries for each model instance when accessing `public_id`, since `DocumentId` is linked through a generic foreign key.

This issue becomes more evident in GraphQL edge and node queries that involve large objects with deeply nested object types and large result sets. To address this, we introduced the `baseapp_core.graphql.DjangoObjectType` abstraction. By leveraging the `query_optimizer` package for Graphene, we dynamically annotate the resolution of these generic foreign keys based on the GraphQL query structure before executing the queryset. This approach prevents query explosions.

While the Public Id strategy still results in more queries than the Legacy mode, the overhead is now acceptable.

We do not currently cover DRF-specific optimizations, since Baseapp does not heavily rely on these types of endpoints. This is something that can be considered in the future.

Whenever making structural changes to Baseapp HashIds or GraphQL-related code, make sure to validate the impact on query performance.
