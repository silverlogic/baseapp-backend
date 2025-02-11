# BaseApp View Action Permissions - Django

This app uses django provided permission and group model and provides the ability to add roles to a django model, and make views from the [django-restframework](https://www.django-rest-framework.org/) check for them. A **Permission** represents the lowest single unit of access. A **Group** is a collection of Permissions. A **Role** can have many Permision Groups, many Permissions and many **Excluded Permissions**. The access of a Role is the aggregation of its single Permissions + the permissions on its **Permission** Groups - its Excluded Permissions.

## Install the package

Install in your environment:

```bash
pip install baseapp-drf-view-action-permissions
```

## Add the app to your project INSTALLED_APPS

```py
INSTALLED_APPS = [
    ...
    "baseapp_drf_view_action_permissions",
]
```

## Add the mixin to your model

```py
from django.db import models
from baseapp_drf_view_action_permissions.mixins import PermissionModelMixin

class User(PermissionModelMixin, models.Model):
    ...
```

## Implement the permission class

```py
from rest_framework import viewsets
from baseapp_drf_view_action_permissions.action import DjangoActionPermissions

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [DjangoActionPermissions, ]
    permission_base = "users" # if not defined the app label would be used
    model_class = User # Only required if viewset not using queryset
    # optional perms_map_action to override default behaviour
    perms_map_action = {
        'custom_action': ['users.list_users']
    }

    def get_queryset(self):
        return User.objects.all()
    ...
```

This permission class will check that the `user` calling an action in the viewset has a **Permission** with the `codename` `{app_label}.{action}_{permission_base|app_label}`. In this example, the viewset will raise a 403 error if the user doesn't have a **Permission** with the codename `users.add_users` and tries to call the `create` action (using a POST method). The same applies to the `list`, `retrieve`, `update` and `destroy` actions. Note that PUT and PATCH requests expect the same `users.change_update` **Permission**, event if DRF maps PUT requests with the _partial_update_ action.

For additional actions added to the viewset with the `@action` decorator, the following `codename` convention is expected if you do not want to manually specify it in the view using `perms_map_action`: `{action_name}_{permission_base|app_label}`. For example, if we update the previous viewset to look like this (assuming the app name is `users`):

```py
class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [ActionPermission]
    permission_base = "users"
    ...

    @action(methods=['GET', 'POST'])
    def lessons(self, *args, **kwargs):
        ...
```

The permission class will expect the user to have a **Permission** with the codename `users.lessons_users` when a GET or POST request is made.

The `perms_map_action` can also accept a method with the following signature `def method_name(user, view, obj=None)`.

```py

def check_object_permission(user, view, obj=None):
    if not obj:
        return True
    return obj.user.id ==  user.id

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [ActionPermission]
    permission_base = "users"
    perms_map_action = {
        'update': ['users.change_users', check_object_permission]
    }
    ...
```

The `DjangoActionPermissions` class will only work with models injected to the `request` by one of the DRF's [authentication mechanisms](https://www.django-rest-framework.org/api-guide/authentication/) as the `user` property.

## Create Permissions

Once you add the module to your project's INSTALLED_APPS, you will get access to a new section on the admin site called **DJANGO-VIEW-ACTION-PERMISSIONS**, with the **Role** table. You can set all the roles that you need there and groups using Django built in groups, but we recommend to create data migrations to ensure that your roles exists in every environment of your app.

### Adding new permission

Django automatically creates four basic permissions for every model, these are `add_{modelname}`, `change_{modelname}`, `view_{modelname}` and `delete_{modelname}`. To add new ones, you can define them in the model meta class. see example below

```py
class User(models.Model):
    ...

    class Meta:
        permissions = [
            ("disable_users", "Can be able to disable users"),
            ("activate_users", "Can be able to activate users"),
        ]
```

After defining the permissions, you need to generate a migration using Django command `./manage.py makemigrations`. Make sure to have generated the migration before any other migration that uses this new permission i.e writing a migration to add the new permission to a group.

If you want to use the default drf list view action make sure to add `view_{modelname}_list` in the permissions list, except you want to specify the permission to use in `perms_map_action`

### Creating migrations for groups

We have provided two utility function to load and remove permissions from group. See example below

```py
from django.db import migrations

from baseapp_drf_view_action_permissions.utils import get_permission_loader, get_permission_remover

permissions = [
    {"name": "Test Group", "permissions": ['list_testmodel', 'disable_testmodel', 'add_testmodel'],},
]


class Migration(migrations.Migration):

    dependencies = [
        ("testapp", "0002_alter_testmodel_options"),
    ]

    operations = [
        migrations.RunPython(get_permission_loader(permissions=permissions), get_permission_remover(permissions=permissions, remove_group=True)),
    ]

```

The above migrations will create a new group if not exists and assign the following permissions. notice the `remove_group=True` this will delete the group on rollback. if this is an update to an existing group make sure to set it to `False`.

## Exclude views from a viewset

If you want to exclude a view from the permission checking logic, you can specify the name of the action in the `permission_exclude_views` property. Example:

```py
class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [ActionPermission]
    permission_base = "users"
    permission_exclude_views = ['retrieve', 'list', 'lessons']
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

Here, the `lessons_other_base` **Permission** would be expected.

# Check permission outside of `DjangoActionPermissions`

You can check user permission using the `has_perm` (for one permission) and `has_perms` (for multiple permissions) method of the user object.

```py
user = User.objects.first()
assert user.has_perm('users.add_users')
assert user.has_perms(['users.change_users', 'vendors.add_client'])

```

Note that super user has all the permissions.

# IP Address Restrictions

To restrict Django admin and all endpoints by Ip address, Add below to the middlewares

```py
MIDDLEWARE = [
    ...
    "django.contrib.auth.middleware.AuthenticationMiddleware", # make sure it's after the authentication middleware
    ...
    "baseapp_drf_view_action_permissions.middleware.RestrictIpMiddleware",
    ...
]
```

To restrict only Django admin, set `IP_RESTRICT_ONLY_DJANGO_ADMIN=True`. If you want to only allow whitelisted IP also set `ALLOW_ONLY_WHITELISTED_IP=True`.

If ALLOW_ONLY_WHITELISTED_IP is False it will allow any Ip that is not specified in Ip Restrictions.

Note: Restriction by role only works in Django admin when using the middleware since user object is not available in middleware when using drf views. Use `IpAddressPermission` on such views.

## Restrict Viewset by Ip

You can also use `IpAddressPermission` to restrict specific or all view actions.

```py
from baseapp_drf_view_action_permissions.action import IpAddressPermission


class DummyIpViewSet(viewsets.GenericViewSet):
    permission_classes =  [IpAddressPermission, ]

    def list(self, *args, **kwargs):
        return response.Response([])

    @decorators.action(methods=["GET"], detail=False, permission_classes=[IpAddressPermission, ])
    def custom_action(self, *args, **kwargs):
        return response.Response({})

```
