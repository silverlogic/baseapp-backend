# CurrentProfile REST Framework Integration

## Overview

This module provides the `CurrentProfileMixin` to enable the same current profile functionality in REST framework views that exists in Django middleware and GraphQL middleware.

## How It Works

The `CurrentProfileMixin` reads the `Current-Profile` header from the request and sets `request.user.current_profile` based on:

1. **No header provided**: Uses the user's default profile (`request.user.profile`)
2. **Header provided**: Attempts to load the profile with the specified ID (relay ID format)
   - Only sets the profile if the user has permission to use it (`use_profile` permission)
   - Falls back to `None` if permission check fails

This replicates the logic from:
- `baseapp_profiles.middleware.CurrentProfileMiddleware` (Django middleware)
- `baseapp_profiles.graphql.middleware.CurrentProfileMiddleware` (GraphQL middleware)

## Usage

### In ViewSets

Add the mixin to your viewset classes:

```python
from baseapp_profiles.rest_framework import CurrentProfileMixin
from rest_framework import viewsets

class MyViewSet(CurrentProfileMixin, viewsets.ModelViewSet):
    queryset = MyModel.objects.all()
    serializer_class = MySerializer
```

### Making Requests

Send the `Current-Profile` header with the relay ID of the profile you want to use:

```bash
curl -H "Authorization: Bearer <token>" \
     -H "Current-Profile: UHJvZmlsZU9iamVjdFR5cGU6MQ==" \
     https://api.example.com/v1/my-endpoint/
```

### Accessing Current Profile

In your view methods, access the current profile via:

```python
def list(self, request):
    current_profile = request.user.current_profile
    # Use the profile...
```

## Example Implementation

See `baseapp.files.rest_framework.files.views.FilesViewSet` for an example:

```python
from baseapp_profiles.rest_framework import CurrentProfileMixin
from rest_framework import viewsets

class FilesViewSet(CurrentProfileMixin, mixins.RetrieveModelMixin, ...):
    """ViewSet for file CRUD operations with current profile support."""
    pass
```

## Notes

- The mixin executes in the `initial()` method, which runs before any view logic
- Authentication must happen before this mixin runs (ensure authentication classes are properly configured)
- The `Current-Profile` header must be whitelisted in CORS settings
