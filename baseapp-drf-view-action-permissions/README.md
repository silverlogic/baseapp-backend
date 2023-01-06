# BaseApp Permissions - Django

This app provides the ability to add permissions, permission groups and roles to a django model, and make views from the [django-restframework](https://www.django-rest-framework.org/) check for them. A **Permission** represents the lowest single unit of access. A **Permission Group** is a collection of Permissions. A **Role** can have many Permision Groups, many Permissions and many **Excluded Permissions**. The access of a Role is the aggregation of its single Permissions + the permissions on its **Permission** Groups - its Excluded Permissions.

## Install the package

Add to `requirements/base.txt` (replacing everything inside brackets):

```bash
django-permissions @ git+https://{BITBUCKET_USERNAME}@bitbucket.org/silverlogic/baseapp-permissions-django.git@{TAG or BRANCH or HASH}
```

## Add the app to your project INSTALLED_APPS

```py
INSTALLED_APPS = [
    ...
    "permissions",
]
```

## Settings (optional)

You can add the following settings to your `settings/base.py`:

```py
SUPERUSER_HAS_ALL_ACTION_PERMISSIONS = True # Makes super users bypass the permissions. Default is False
```

## Add the mixin to your model

```py
from django.db import models
from permissions.mixins import PermissionsModelMixin

class User(PermissionsModelMixin, models.Model):
    ...
```

## Implement the permission class and set the base slug

```py
from rest_framework import viewsets
from permissions.permissions import ActionPermission

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [ActionPermission]
    permission_base = "users"
    ...
```
This permission class will check that the `user` calling an action in the viewset has a **Permission** with the `slug` `{permission_base}_{action}`. In this example, the viewset will raise a 403 error if the user doesn't have a **Permission** with the slug `users_create` and tries to call the `create` action (using a POST method). The same applies to the `list`, `retrieve`, `update` and `destroy` actions. Note that PUT and PATCH requests expect the same `{permission_base}_update` **Permission**, event if DRF maps PUT requests with the *partial_update* action.

For additional actions added to the viewset with the `@action` decorator, the following `slug` convention is expected: `{permission_base}_{action_name}_{request_method}`. For example, if we update the previous viewset to look like this:
```py
class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [ActionPermission]
    permission_base = "users"
    ...

    @action(methods=['GET', 'POST'])
    def lessons(self, *args, **kwargs):
        ...
```
The permission class will expect the user to have a **Permission** with the slug `users_lessons_list` when a GET request is made and one with the slug `users_lessons_create` when a POST request is made.


The `ActionPermission` class will only work with models injected to the `request` by one of the DRF's [authentication mechanisms](https://www.django-rest-framework.org/api-guide/authentication/) as the `user` property.

## Create Permissions
Once you add the module to your project's INSTALLED_APPS, you will get access to a new section on the admin site called **DJANGO-PERMISSIONS**, with the **Role**, **Permission** and **Permission Group** tables. You can set all the permissions and roles that you need there, but we recommend to create data migrations to ensure that your roles and permissions exists in every environment of your app.

## Exclude views from a viewset
If you want to exclude a view from the permission checking logic, you can specify either the expected slug or the name of the action in the `permission_exclude_views` property. Example:
```py
class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [ActionPermission]
    permission_base = "users"
    permission_exclude_views = ['retrieve', 'list', 'users_lessons_list']
    ...

    @action(methods=['GET', 'POST'])
    def lessons(self, *args, **kwargs):
        ...

```

## Specific permission_base string for a specific view
If you want to override the `permission_base` for a specific custom action, you can. Example:

```py
class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [ActionPermission]
    permission_base = "users"
    ...

    @action(methods=['GET'], permission_base='other_base')
    def lessons(self, *args, **kwargs):
        ...

```
Here, the `other_base_lessons_list` **Permission** would be expected.

# To do

 - [ ] Add tests for superuser setting
 - [ ] Implement permission group inheritance/hierarchy
 - [ ] Migrate auto-generation logic from WAYS (experimental)
 - [ ] Allow to check permissions outside of `ActionPermission` or make the model instance source configurable (currently not needed by any project)