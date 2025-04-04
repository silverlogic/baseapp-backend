# BaseApp Pages

Reusable app to handle pages, URL's paths and metadata. It provides useful models and GraphQL Interfaces.

## Whats missing
- [ ] Allow for custom settings.LANGUAGES per project
- [ ] Make create migration work with TranslatedField

Currenly if you have a different set of languages in your projects it will create a new migration changing the fields. So if you have a migration check test it will fail because the `settings.LANGUAGES` are different.

## How to install:

This package requires to following packages to be installed:

- [baseapp-comments](../baseapp-comments/README.md)

And install the package with `pip install baseapp-backend`.

And its 3rd-party dependencies with `pip install django-quill-editor 0.1.42`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_pages` and `django_quill` to your project's `INSTALLED_APPS` and run `./manage.py migrate` as any other django model:

```python
INSTALLED_APPS = [
    'baseapp_pages',
    'django_quill',
]
```

Add `django.middleware.locale.LocaleMiddleware` to the `MIDDLEWARE` list in your django settings file. [Check django's documentation for more information](https://docs.djangoproject.com/en/5.0/topics/i18n/translation/#how-django-discovers-language-preference).

Add `baseapp_pages.permissions.PagesPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file.

Expose `PagesMutations` and `PagesQuery` in your GraphQL/graphene endpoint, like:

```python
from baseapp_pages.graphql.mutations import PagesMutations
from baseapp_pages.graphql.queries import PagesQuery

class Query(graphene.ObjectType, PagesQuery):
    pass

class Mutation(graphene.ObjectType, PagesMutations):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```

This will expose `urlPath` and `page` query.

### `urlPath` query:

Example:

```graphql
{
    urlPath(path: '/about') {
        path
        language
        target {
            metadata {
                metaTitle
            }

            ... on Page {
                title
            }
        }
    }
}
```

### PageInterface

`PageInterface` is a GraphQL interface that can be used to query for pages. It has the following fields:

- `urlPath` return the active `URLPath`
- `urlPaths` return all `URLPath` for the object, including inactive ones and in other languages
- `metadata` return the `Metadata` for the object

ObjectTypes that implements `PageInterface` is required to implement a resolve for `metadata` like this:

```python
from django.utils.translation import get_language
from baseapp_core.graphql import DjangoObjectType
from baseapp_pages.graphql import PageInterface, MetadataObjectType


class MyModelObjectType(DjangoObjectType):
    class Meta:
        model = MyModel
        interfaces = (relay.Node, PageInterface)

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        return MetadataObjectType(
            meta_title=instance.title,
            meta_description=instance.body[:160],
            meta_og_image=instance.image.url,
            meta_robots='noindex,nofollow'
        )
```

If you want to support `Metadata` being manually set or overriden in the admin you can use the following code:

```python
class MyModelObjectType(DjangoObjectType):
    # ...

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        target_content_type = ContentType.objects.get_for_model(instance)
        metadata = MetadataObjectType._model.objects.filter(
            target_content_type=target_content_type,
            target_object_id=self.id,
            language=get_language(),
        ).first()
        if not metadata:
            return MetadataObjectType(
                meta_title=instance.title,
                # ...
            )
        return metadata
```

## How to develop

General development instructions can be found in [main README](..#how-to-develop).
