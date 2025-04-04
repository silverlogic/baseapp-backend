# BaseApp Follows

Reusable app to enable any model follow/unfollow any model.


## Requirements:
```
- **baseapp-core** >= 0.2.3
```

Run `pip install baseapp-follows`
And make sure to add the frozen version to your `requirements/base.txt` file

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_follows` to your project's `INSTALLED_APPS`

Now make sure all models you'd like to get follows also inherits `FollowableModel`, like:

```python
from baseapp_follows.models import FollowableModel

class User(models.Model, FollowableModel):
```

Also make sure your GraphQL object types extends `FollowsInterface` interface:

```python
from baseapp_follows.graphql.object_types import FollowsInterface

class UserNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, FollowsInterface)
```

Expose `FollowsMutations` in your GraphQL/graphene endpoint, like:

```python
from baseapp_follows.graphql.mutations import FollowsMutations

class Mutation(graphene.ObjectType, FollowsMutations):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```

This will expose `followToggle` mutation and add fields and connections to all your GraphqlQL Object Types using interface `FollowsInterface`.

Example:

```graphql
    mutation FollowButtonMutation($input: FollowToggleInput!) {
        followToggle(input: $input) {
            follow {
                node {
                id
                }
            }
            target {
                id
                followersCount
                isFollowedByMe
            }
            actor {
                id
                followingCount
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
pip install -e baseapp-backend/baseapp-follows
```

The `-e` flag will make it like any change you make in the cloned repo files will effect into the project.