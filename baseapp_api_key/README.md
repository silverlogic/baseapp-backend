# BaseApp API Key

Reusable Django app for secure API key authentication and management. This package provides encrypted API key storage with support for both REST Framework and GraphQL authentication.

## Features

- **Encrypted API Key Storage**: API keys are encrypted using AES-SIV encryption before being stored in the database
- **REST Framework Authentication**: Built-in authentication classes for Django REST Framework
- **GraphQL Authentication**: Middleware and consumer classes for GraphQL WebSocket authentication
- **Permission Classes**: Ready-to-use permission classes for API key validation
- **Admin Interface**: Django admin integration with automatic API key generation
- **Management Commands**: CLI tools for encryption key generation and rotation
- **Expiration Support**: Optional expiry dates for API keys with automatic validation
- **Key Rotation**: Support for rotating encryption keys without losing existing API keys

## How to install

Install in your environment:

```bash
pip install baseapp-backend[api_key]
```

And run provision or manually `pip install -r requirements/base.ext`

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_api_key` to your project's `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... other apps
    'baseapp_api_key',
]
```

### Configuration

Add the required settings to your Django settings:

```python
# Required: Encryption key for API keys (generate using management command)
BA_API_KEY_ENCRYPTION_KEY = env("BA_API_KEY_ENCRYPTION_KEY")

# Required: HTTP header name for API key authentication
BA_API_KEY_REQUEST_HEADER = env("BA_API_KEY_REQUEST_HEADER", default="HTTP_API_KEY")
```

Generate an encryption key using the management command:

```bash
python manage.py api_key --model baseapp_api_key.APIKey --generate_encryption_key
```

### Basic Usage

#### Creating API Keys

API keys can be created through the Django admin interface or programmatically:

```python
from baseapp_api_key.models import APIKey

# Create an API key for a user
api_key = APIKey.objects.create(
    user=user,
    name="My API Key",
    expiry_date=None  # Optional expiry date
)

# The encrypted API key is automatically generated and stored
```

#### REST Framework Authentication

Use the provided authentication class in your Django REST Framework views:

```python
from rest_framework.views import APIView
from baseapp_api_key.rest_framework.authentication import APIKeyAuthentication
from baseapp_api_key.rest_framework.permissions import HasAPIKey

class MyAPIView(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey]  # or use IsAuthenticated
    
    def get(self, request):
        # User is authenticated via API key
        return Response({'user': request.user.username})
```

#### GraphQL Authentication

For GraphQL WebSocket authentication, use the provided consumer:

```python
# routing.py
from baseapp_api_key.graphql.consumers import GraphqlWsAPIKeyAuthenticatedConsumer

websocket_urlpatterns = [
    path("graphql/", GraphqlWsAPIKeyAuthenticatedConsumer.as_asgi()),
]
```

For GraphQL HTTP requests, use the middleware:

```python
# In your GraphQL schema
from baseapp_api_key.graphql.middleware import APIKeyAuthentication

schema = graphene.Schema(
    query=Query,
    mutation=Mutation,
    middleware=[APIKeyAuthentication()]
)
```

#### Making API Requests

Include the API key in the configured header:

```bash
# Using curl
curl -H "API-Key: BA-your-64-character-api-key-here" \
     https://your-api.com/api/endpoint/

# Using Python requests
import requests

headers = {
    'API-Key': 'BA-your-64-character-api-key-here'
}
response = requests.get('https://your-api.com/api/endpoint/', headers=headers)
```

### Management Commands

#### Generate Encryption Key

Generate a new encryption key for your environment:

```bash
python manage.py api_key --model baseapp_api_key.APIKey --generate_encryption_key
```

#### Rotate Encryption Keys

Rotate existing encryption keys (useful for security key rotation):

```bash
python manage.py api_key --model baseapp_api_key.APIKey --rotate_encryption_key OLD_KEY NEW_KEY
```

This command will:
1. Decrypt all existing API keys using the old key
2. Re-encrypt them using the new key
3. Update the database with the newly encrypted values

### Custom API Key Models

You can extend the base API key model for your specific needs:

```python
from baseapp_api_key.models import BaseAPIKey

class CustomAPIKey(BaseAPIKey):
    # Add custom fields
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=dict)
    
    # Use custom prefix
    objects = BaseAPIKeyManager(api_key_prefix="CUSTOM")
    
    class Meta(BaseAPIKey.Meta):
        abstract = False
```

Then create corresponding authentication classes:

```python
from baseapp_api_key.rest_framework.authentication import BaseAPIKeyAuthentication

class CustomAPIKeyAuthentication(BaseAPIKeyAuthentication):
    APIKeyModel = CustomAPIKey
```

### Security Features

#### Encryption
- API keys are encrypted using AES-SIV (Synthetic Initialization Vector) encryption
- Only encrypted values are stored in the database
- Original API keys are never stored in plaintext

#### Key Format
- API keys follow the format: `{PREFIX}-{64-character-random-string}`
- Default prefix is "BA" but can be customized per model
- Keys are generated using Django's cryptographically secure random string generator

#### Expiration
- Optional expiry dates with automatic validation
- Expired keys are rejected during authentication
- QuerySet methods automatically filter expired keys

#### Key Rotation
- Supports rotating encryption keys without losing existing API keys
- Management command handles the rotation process safely
- Maintains data integrity during key rotation

## Admin Interface

The package provides a Django admin interface for managing API keys:

- **List View**: Shows API key ID, user, name, and expiration status
- **Create/Edit**: Automatically generates encrypted API keys on creation
- **Security**: Displays the unencrypted API key only once during creation
- **User Default**: Sets the current admin user as the default key owner

## Testing

The package includes comprehensive test coverage:

```bash
# Run API key tests
python manage.py test baseapp_api_key

# Run with coverage
coverage run --source='.' manage.py test baseapp_api_key
coverage report
```

## How to develop

Clone the project inside your project's backend dir:

```bash
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```bash
pip install -e baseapp-backend/baseapp_api_key
```

The `-e` flag will make it so any changes you make in the cloned repo files will affect the project.

## API Reference

### Models

#### `BaseAPIKey`
Abstract base model for API keys.

**Fields:**
- `user`: ForeignKey to AUTH_USER_MODEL
- `name`: CharField for API key identification
- `encrypted_api_key`: BinaryField storing encrypted key
- `expiry_date`: Optional DateField for key expiration
- `created`: Auto-generated creation timestamp
- `modified`: Auto-generated modification timestamp

**Properties:**
- `is_expired`: Boolean indicating if the key has expired

#### `APIKey`
Concrete implementation of BaseAPIKey ready for use.

### Managers

#### `BaseAPIKeyManager`
Custom manager providing encryption and key management functionality.

**Methods:**
- `generate_encryption_key()`: Generate a new AES-SIV encryption key
- `generate_unencrypted_api_key()`: Generate a new unencrypted API key string
- `encrypt(value, encryption_key=None)`: Encrypt a value using AES-SIV
- `decrypt(encrypted_value, encryption_key=None)`: Decrypt an encrypted value
- `rotate_encryption_key(old_key, new_key)`: Rotate encryption keys for all records

### Authentication Classes

#### REST Framework
- `BaseAPIKeyAuthentication`: Abstract authentication class
- `APIKeyAuthentication`: Concrete implementation for APIKey model

#### GraphQL
- `APIKeyAuthentication`: Middleware for GraphQL HTTP requests
- `BaseGraphqlWsAPIKeyAuthenticatedConsumer`: WebSocket consumer base class
- `GraphqlWsAPIKeyAuthenticatedConsumer`: Concrete WebSocket consumer

### Permission Classes

#### REST Framework
- `BaseHasAPIKey`: Abstract permission class
- `HasAPIKey`: Concrete permission class for APIKey validation