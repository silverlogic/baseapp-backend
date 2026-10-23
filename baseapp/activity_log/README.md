# BaseApp Activity Log

This app exposes an API to view user's activities that are being tracked by the system.

## Installation

### Requirements:

You need to have [django-pghistory](https://github.com/Opus10/django-pghistory) installed in your project and models that you want to track should be tracked by pghistory:

```python
import pghistory

@pghistory.track()
class TrackedModel(models.Model):
    int_field = models.IntegerField()
    text_field = models.TextField()
```

Add `baseapp.activity_log` to your `INSTALLED_APPS` setting:

```python
INSTALLED_APPS = [
    ...
    'baseapp.activity_log',
]
```

Make sure you have the pghistory middleware from baseapp_core configured:

```python
MIDDLEWARE = [
    ...
    'baseapp_core.middleware.HistoryMiddleware',
]
```

Add `ActivityLogPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in the `settings.py` file:

```python
AUTHENTICATION_BACKENDS = [
    ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp.activity_log"),
]
```

Make sure your graphql.py main file is loading queries, mutations and subscriptions from plugin_registry.

## Usage

By default users only have access to public activities. To log an activity as public use the `set_public_activity` in the shared service:

```python
from baseapp_core.plugins import shared_services

def create_comment(request, body):
    # ...
    if service := shared_services.get("activity_log"):
        service.set_public_activity(verb="baseapp_comments.add_comment")
```

### Hiding event diffs

The `diff` of an event (`NodeLogEvent.diff`) holds the values that changed, for example the body of
a comment. By default anyone who can see a public activity can read its diffs. Set
`BASEAPP_ACTIVITY_LOG_PUBLIC_NODE_DIFF = False` to return the diff to superusers only, like `data`:

```python
BASEAPP_ACTIVITY_LOG_PUBLIC_NODE_DIFF = True  # default True
```

To grant it to more users, subclass `ActivityLogPermissionsBackend` and handle
`activity_log.view_nodelogevent-diff` (`obj` is the event).

### GraphQL

This packages provides the following interfaces that can be used to expose the activity logs for user, profile and specific models:

- `NodeActivityLogInterface`
- `UserActivityLogInterface`
- `ProfileActivityLogInterface`

This app also exposes a query to fetch a global list of activities:

```graphql
{
  activityLogs(visibility: PUBLIC, first: 10) {
    edges {
      node {
        id
        verb
        profile {
          name
        }
        events {
          diff
          label
          obj {            
            ... on Comment {
              body
            }
          }
        }
        createdAt
      }
    }
  }
}
```
