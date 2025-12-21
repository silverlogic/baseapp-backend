# Baseapp Core - HashIds

HashIds provides a set of abstractions and helper functions designed to help models across the system avoid exposing sequential integer primary keys to external services, such as frontend applications. Compared to sequential PKs, public IDs make it significantly harder to infer other records, which is generally a safer and more appropriate approach than exposing raw database primary keys.

To omit internal PKs, models must be made compatible with HashIds, and the appropriate abstractions must be used when defining queries, mutations, or subscriptions in Graphene, as well as when creating new endpoints in DRF.


## Making Models Compatible With HashIds

This is fairly simple. We use the DocumentId pattern (see [Baseapp Core](../README.md#documentid-model) for more details). You just need to ensure that any model that should omit its internal integer primary key extends the `baseapp_core.models.DocumentIdMixin` abstraction.


## Making Graphene ObjectTypes Compatible With HashIds

This is also very simple. You just need to include the `baseapp_core.graphql.Node` interface in the ObjectType interfaces.

```python
from baseapp_core.graphql import Node as RelayNode
from baseapp_chats.graphql.interfaces import ChatRoomsInterface

class ProfileObjectType(DjangoObjectType):
    class Meta:
        interfaces = (RelayNode, ChatRoomsInterface)
```

