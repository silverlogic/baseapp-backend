# BaseApp Ratings

Reusable app to enable User's ratings on any model.

## How to install:

Install in your environment:

```bash
pip install baseapp-ratings
```

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_ratings` to your project's `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    # ...
    "baseapp_ratings",
    # ...
]
```

Add `baseapp_ratings.permissions.RatingsPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file.

```python
AUTHENTICATION_BACKENDS = [
    # ...
    "baseapp_ratings.permissions.RatingsPermissionsBackend",
    # ...
]
```

Now make sure all models you'd like to get ratings also inherits `RatableModel`, like:

```python
from baseapp_ratings.models import RatableModel

class Comment(models.Model, RatableModel):
    body = models.Textfield()
```

Also make sure your GraphQL object types extends `RatingsInterface` interface:

```python
from baseapp_ratings.graphql.object_types import RatingsInterface

class CommentNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, RatingsInterface)
```

Expose `RatingsMutations` and `RatingsQueries` in your GraphQL/graphene endpoint, like:

```python
from baseapp_ratings.graphql.mutations import RatingsMutations
from baseapp_ratings.graphql.queries import RatingsQueries

class Query(graphene.ObjectType, RatingsQueries):
    pass

class Mutation(graphene.ObjectType, RatingsMutations):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```

This will expose `rateCreate` mutation and add fields and connections to all your GraphqlQL Object Types using interface `RatingsInterface`.

Example:

```graphql
{
    user(id: $id) {
        id
        ratingsCount
        ratingsSum
        ratingsAverage
        ratings(first: 10) {
            edges {
                node {
                    user {
                        name
                    }
                    value
                }
            }
        }
    }
}
```

## How to to customize the Rating model

In some cases you may need to extend Rating model, and we can do it following the next steps:

Start by creating a barebones django app:

```
mkdir my_project/ratings
touch my_project/ratings/__init__.py
touch my_project/ratings/models.py
```

Your `models.py` will look something like this:

```python
from django.db import models
from django.utils.translation import gettext_lazy as _

from baseapp_ratings.models import AbstractBaseRate

class Rate(AbstractBaseRate):
    custom_field = models.CharField(null=True)
```

Now make your to add your new app to your `INSTALLED_APPS` and run `makemigrations` and `migrate` like any normal django app.

Now in your `settings/base.py` make sure to tell baseapp-ratings what is your custom model for Rating:

```python
BASEAPP_RATINGS_RATE_MODEL = 'ratings.Rate'
```

If you want to define a maximum value for your rating:

```python
BASEAPP_MAX_RATING_VALUE = 5
```

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp-ratings
```

The `-e` flag will make it like any change you make in the cloned repo files will effect into the project.