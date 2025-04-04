# BaseApp Reactions

Reusable app to enable User's reactions on any model, features like like/dislike or any other reactions type, customizable for project's needs.

## How to install:

Install in your environment:

```bash
pip install baseapp-reactions
```

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_reactions` to your project's `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    # ...
    "baseapp_reactions",
    # ...
]
```

Add `baseapp_reactions.permissions.ReactionsPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file.

```python
AUTHENTICATION_BACKENDS = [
    # ...
    "baseapp_reactions.permissions.ReactionsPermissionsBackend",
    # ...
]
```

Now make sure all models you'd like to get reactions also inherits `ReactableModel`, like:

```python
from baseapp_reactions.models import ReactableModel

class Comment(models.Model, ReactableModel):
    body = models.Textfield()
```

Also make sure your GraphQL object types extends `ReactionsInterface` interface:

```python
from baseapp_reactions.graphql.object_types import ReactionsInterface

class CommentNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, ReactionsInterface)
```

Expose `ReactionsMutations` and `ReactionsQueries` in your GraphQL/graphene endpoint, like:

```python
from baseapp_reactions.graphql.mutations import ReactionsMutations
from baseapp_reactions.graphql.queries import ReactionsQueries

class Query(graphene.ObjectType, ReactionsQueries):
    pass

class Mutation(graphene.ObjectType, ReactionsMutations):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```

This will expose `reactionToggle` mutation and add fields and connections to all your GraphqlQL Object Types using interface `ReactionsInterface`.

Example:

```graphql
{
    comment(id: $id) {
        id
        reactionsCount {
            LIKE
            DISLIKE
            total
        }
        reactions(first: 10) {
            edges {
                node {
                    reactionType
                    user {
                        name
                    }
                }
            }
        }
    }
}
```

## How to to customize the Reaction model

In some cases you may need to extend Reaction model, and we can do it following the next steps:

Start by creating a barebones django app:

```
mkdir my_project/reactions
touch my_project/reactions/__init__.py
touch my_project/reactions/models.py
```

Your `models.py` will look something like this:

```python
from django.db import models
from django.utils.translation import gettext_lazy as _

from baseapp_reactions.models import AbstractBaseReaction

class Reaction(AbstractBaseReaction):
    custom_field = models.CharField(null=True)

    class ReactionTypes(models.IntegerChoices):
        LIKE = 1, _("like")
        DISLIKE = -1, _("dislike")

        @property
        def description(self):
            return self.label
```

Now make your to add your new app to your `INSTALLED_APPS` and run `makemigrations` and `migrate` like any normal django app.

Now in your `settings/base.py` make sure to tell baseapp-reactions what is your custom model for Reaction:

```python
BASEAPP_REACTIONS_REACTION_MODEL = 'reactions.Reaction'
```

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp-reactions
```

The `-e` flag will make it like any change you make in the cloned repo files will effect into the project.