# BaseApp Blocks

Reusable app to enable any model block/unblock any model.


## Requirements:
```
- **baseapp-core** >= 0.2.3
```

Run `pip install baseapp-blocks`
And make sure to add the frozen version to your `requirements/base.txt` file

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_blocks` to your project's `INSTALLED_APPS`

Add `baseapp_blocks.permissions.BlocksPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file.


Now make sure all models you'd like to get blocks also inherits `BlockableModel`, like:

```python
from baseapp_blocks.models import BlockableModel

class User(models.Model, BlockableModel):
```

Also make sure your GraphQL object types extends `BlocksInterface` interface:

```python
from baseapp_blocks.graphql.object_types import BlocksInterface

class UserNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, BlocksInterface)
```

Expose `BlocksMutations` in your GraphQL/graphene endpoint, like:

```python
from baseapp_blocks.graphql.mutations import BlocksMutations

class Mutation(graphene.ObjectType, BlocksMutations):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```

This will expose `blockToggle` mutation and add fields and connections to all your GraphqlQL Object Types using interface `BlocksInterface`.

Example:

```graphql
    mutation BlockButtonMutation($input: BlockToggleInput!) {
        blockToggle(input: $input) {
            block {
                node {
                id
                }
            }
            target {
                id
                blockersCount
                isBlockedByMe
            }
            actor {
                id
                blockingCount
            }
        }
    }
```

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp-blocks
```

The `-e` flag will make it like any change you make in the cloned repo files will effect into the project.