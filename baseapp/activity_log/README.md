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

Add `HistoryMiddleware` to the `MIDDLEWARE` list in the `settings.py` file:

```python
MIDDLEWARE = [
    ...
    'baseapp.activity_log.middleware.HistoryMiddleware',
]
```

Add `ActivityLogPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in the `settings.py` file:

```python
AUTHENTICATION_BACKENDS = [
    ...
    "baseapp.activity_log.permissions.ActivityLogPermissionsBackend",
]
```

Add `ActivityLogQueries` to your GraphQL schema:

```python
from baseapp.activity_log.schema import ActivityLogQueries

class Query(ActivityLogQueries, graphene.ObjectType):
    pass

schema = graphene.Schema(query=Query)
```

## Usage

By default users only have access to public activities. To log an activity as public use the `set_public_activity` function:

```python
from baseapp.activity_log.context import set_public_activity

def create_comment(request, body):
    # ...
    set_public_activity(verb="baseapp_comments.add_comment")
```

### GraphQL

This packages provides the following interfaces that can be used to expose the activity logs for user, profile and specific models:

- `NodeActivityLogInterface`
- `UserActivityLog`
- `ProfileActivityLog`

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
