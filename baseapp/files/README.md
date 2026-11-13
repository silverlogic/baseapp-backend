# BaseApp Files - S3 Direct Multipart Upload

REST API endpoints for S3 direct multipart uploads, allowing clients to upload large files directly to S3 without going through the Django backend.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Production (S3)](#production-s3)
  - [Development (Local Storage)](#development-local-storage)
- [API Usage](#api-usage)
  - [Complete Upload Flow](#complete-upload-flow)
  - [API Endpoints](#api-endpoints)
- [Client Implementation](#client-implementation)
- [Private Files and Anonymous Uploads](#private-files-and-anonymous-uploads)
- [Protected Downloads](#protected-downloads)
- [Background Tasks](#background-tasks)
- [Troubleshooting](#troubleshooting)
- [Advanced Topics](#advanced-topics)

## Overview

This module provides S3-compatible multipart upload functionality with:

- **Direct S3 uploads** - Files upload directly to S3, not through Django
- **Presigned URLs** - Secure, time-limited upload URLs
- **Automatic storage detection** - Works with S3 in production, local storage in dev/test
- **Parent object support** - Attach files to any model (posts, comments, etc.)
- **Automatic cleanup** - Celery task cleans up expired/abandoned uploads

### Architecture

```
Client → Backend (initiate) → S3 Presigned URLs
Client → S3 (upload parts directly)
Client → Backend (complete) → File record created
```

## Installation

### 1. Run Migration

After deploying the code, run the migration to add upload tracking fields:

```bash
# Using docker compose
docker compose exec backend python manage.py migrate files

# Or directly
python manage.py migrate files
```

This adds the following fields to the File model:
- `upload_status` - Track upload state
- `upload_id` - S3 multipart upload ID
- `total_parts` - Number of parts
- `uploaded_parts` - JSON tracking ETags
- `upload_expires_at` - Expiration timestamp

`file_size` is a `PositiveBigIntegerField`, so files over 2 GB fit. A project with its own concrete
`File` model needs `python manage.py makemigrations files` after upgrading to pick that up.

### 2. URLs Already Configured

The URLs are automatically included in your project via `testproject/urls.py`.

Available endpoints:
```
POST   /v1/files/uploads              - Initiate upload
POST   /v1/files/uploads/{id}/complete - Complete upload
DELETE /v1/files/uploads/{id}         - Abort upload
GET    /v1/files                      - List files
GET    /v1/files/{id}                 - Retrieve file
PATCH  /v1/files/{id}                 - Update file metadata
DELETE /v1/files/{id}                 - Delete file
POST   /v1/files/{id}/set-parent      - Set parent relationship
```

## Configuration

### Production (S3)

#### 1. Install boto3 (if not already installed)

```bash
pip install boto3
```

#### 2. Configure Django Settings

Add to your `settings.py` or environment variables:

```python
# AWS S3 Configuration
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='us-east-1')

# File upload settings
MAX_FILE_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024  # 5GB default
FILE_UPLOAD_PRESIGNED_URL_EXPIRATION = 3600  # 1 hour

# Optional: Use S3 as default storage
STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
```

#### 3. Environment Variables

Create or update your `.env` file:

```bash
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=us-east-1
```

#### 4. S3 Bucket Configuration

Ensure your S3 bucket has the correct CORS configuration:

```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
        "AllowedOrigins": ["https://yourdomain.com"],
        "ExposeHeaders": ["ETag"],
        "MaxAgeSeconds": 3000
    }
]
```

**Important**: The `ExposeHeaders: ["ETag"]` is required so clients can read ETags from S3 responses.

### Development (Local Storage)

No additional configuration needed! The system automatically detects local storage and provides a fallback implementation.

**How it works:**
- Storage factory checks if the files storage (`BASEAPP_FILES_STORAGE`, `default_storage` unless set) is `S3Boto3Storage`
- If not S3, uses `LocalUploadHandler` automatically
- Local handler stores parts in `temp_uploads/` under the storage's location (`MEDIA_ROOT` by default)
- Parts are combined on completion

**Note**: Local storage doesn't support true direct uploads - it's a simplified fallback for development/testing only.

## API Usage

### Complete Upload Flow

#### 1. Initiate Upload

**Request:**
```bash
POST /v1/files/uploads
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
    "file_name": "large-video.mp4",
    "file_size": 104857600,
    "file_content_type": "video/mp4",
    "num_parts": 20,
    "part_size": 5242880,
    "parent_id": "b3c5…-document-public-id"  // optional (DocumentId public_id of the parent)
}
```

**Response:**
```json
{
    "id": 456,
    "upload_id": "abc123xyz...",
    "presigned_urls": [
        {
            "part_number": 1,
            "url": "https://bucket.s3.amazonaws.com/...?signature=..."
        },
        {
            "part_number": 2,
            "url": "https://bucket.s3.amazonaws.com/...?signature=..."
        }
        // ... up to 20 parts
    ],
    "expires_in": 3600,
    "upload_status": "uploading"
}
```

**Calculating Parts:**
```python
import math

file_size = 104857600  # 100 MB
part_size = 5242880    # 5 MB (minimum for S3)
num_parts = math.ceil(file_size / part_size)  # 20 parts
```

#### 2. Upload Parts Directly to S3

For each presigned URL, upload the corresponding file chunk using HTTP PUT:

```javascript
// Example with fetch API
const part_number = 1;
const presigned_url = presigned_urls[0].url;
const chunk = file.slice(start, end);

const response = await fetch(presigned_url, {
    method: 'PUT',
    body: chunk,
    headers: {
        'Content-Type': file_content_type
    }
});

// IMPORTANT: Save the ETag from response headers
const etag = response.headers.get('ETag').replace(/"/g, '');
```

**Important Notes:**
- Upload to presigned URLs with HTTP PUT (not POST)
- S3 returns an ETag header for each part - you MUST save these
- ETags are required to complete the upload
- Upload parts in any order (parallel uploads supported)

#### 3. Complete Upload

Once all parts are uploaded, send the completion request with ETags:

**Request:**
```bash
POST /v1/files/uploads/456/complete
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
    "parts": [
        {"part_number": 1, "etag": "abc123..."},
        {"part_number": 2, "etag": "def456..."},
        {"part_number": 3, "etag": "ghi789..."}
        // ... all parts with their ETags
    ]
}
```

**Response:**
```json
{
    "id": 456,
    "file_name": "large-video.mp4",
    "file_size": 104857600,
    "file_content_type": "video/mp4",
    "url": "https://bucket.s3.amazonaws.com/files/uuid.mp4",
    "upload_status": "completed",
    "created_by": 1,
    "created_by_name": "John Doe",
    "created": "2025-12-29T10:00:00Z",
    "parent_id": "b3c5…-document-public-id"
}
```

#### 4. (Optional) Set Parent Later

If you didn't specify a parent during initiation, you can set it later:

**Request:**
```bash
POST /v1/files/456/set-parent
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
    "parent_id": "b3c5…-document-public-id"
}
```

A file is attached as soon as its upload starts when `parent_id` is given, but it only counts as
one of the object's files once the upload completes: `files` and `filesCount` (GraphQL, the
`FilesInterface`) leave out pending, uploading, failed and aborted uploads.

**Upgrading:** the counts are kept by database triggers, so a project with its own concrete
`File` model needs `python manage.py makemigrations files` once. Existing counts correct
themselves the next time a file of that object changes; `recalculate_files_count(obj)` refreshes
one right away.

### API Endpoints

#### Initiate Upload
```
POST /v1/files/uploads
```

**Parameters:**
- `file_name` (string, required) - Original filename
- `file_size` (integer, required) - Total file size in bytes
- `file_content_type` (string, required) - MIME type (e.g., "video/mp4")
- `num_parts` (integer, required) - Number of parts (1-10,000)
- `part_size` (integer, required) - Size of each part in bytes (min 5MB for multipart)
- `parent_id` (UUID, optional) - `DocumentId` public_id of the parent object

**Validation:**
- File size must not exceed `MAX_FILE_UPLOAD_SIZE` (default 5GB)
- Part size must be at least 5MB for multipart uploads (S3 requirement)
- Number of parts must be between 1 and 10,000
- File size must match parts: `(num_parts - 1) * part_size <= file_size <= num_parts * part_size`

#### Complete Upload
```
POST /v1/files/uploads/{id}/complete
```

**Parameters:**
- `parts` (array, required) - Array of objects with:
  - `part_number` (integer) - Part number (1-indexed)
  - `etag` (string) - ETag from S3 response

**Requirements:**
- All parts must be included
- Part numbers must be sequential (1, 2, 3, ...)
- ETags must match S3-uploaded parts
- Only file owner can complete upload

#### Abort Upload
```
DELETE /v1/files/uploads/{id}
```

**Notes:**
- Cleans up S3 multipart upload
- Marks file as "aborted"
- Only file owner can abort
- Prevents charges for incomplete S3 uploads

#### List Files
```
GET /v1/files
```

**Query Parameters:**
- `status` (string, optional) - Filter by upload_status (default: "completed")
- `parent_id` (UUID, optional) - Filter by parent `DocumentId` public_id

**Notes:**
- Returns only user's own files (unless staff)
- Includes only completed files by default
- Use `?status=uploading` to see in-progress uploads

#### Retrieve File
```
GET /v1/files/{id}
```

#### Update File Metadata
```
PATCH /v1/files/{id}
```

**Editable fields:**
- `name` - Display name
- `description` - File description

**Read-only fields:**
- `file_name`, `file_size`, `file_content_type` - Set during upload
- `upload_status` - Managed by system

#### Delete File
```
DELETE /v1/files/{id}
```

**Notes:**
- Only file owner can delete
- Deletes database record
- Does NOT delete S3 object (by design, for safety)

#### Set Parent
```
POST /v1/files/{id}/set-parent
```

**Parameters:**
- `parent_id` (UUID, required) - `DocumentId` public_id of the parent object

## Client Implementation

### JavaScript Example (Complete Flow)

```javascript
class MultipartUploader {
    constructor(apiUrl, token) {
        this.apiUrl = apiUrl;
        this.token = token;
    }

    async uploadFile(file, parentId = null) {
        // 1. Calculate parts
        const partSize = 5 * 1024 * 1024; // 5MB
        const numParts = Math.ceil(file.size / partSize);

        // 2. Initiate upload
        const initResponse = await fetch(`${this.apiUrl}/v1/files/uploads`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_name: file.name,
                file_size: file.size,
                file_content_type: file.type,
                num_parts: numParts,
                part_size: partSize,
                parent_id: parentId
            })
        });

        const { id, upload_id, presigned_urls } = await initResponse.json();

        // 3. Upload parts to S3
        const parts = [];
        for (let i = 0; i < numParts; i++) {
            const start = i * partSize;
            const end = Math.min(start + partSize, file.size);
            const chunk = file.slice(start, end);

            const partResponse = await fetch(presigned_urls[i].url, {
                method: 'PUT',
                body: chunk
            });

            // Extract ETag (remove quotes)
            const etag = partResponse.headers.get('ETag').replace(/"/g, '');

            parts.push({
                part_number: i + 1,
                etag: etag
            });

            // Optional: Report progress
            const progress = ((i + 1) / numParts) * 100;
            console.log(`Upload progress: ${progress.toFixed(1)}%`);
        }

        // 4. Complete upload
        const completeResponse = await fetch(
            `${this.apiUrl}/v1/files/uploads/${id}/complete`,
            {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ parts })
            }
        );

        return await completeResponse.json();
    }

    async abortUpload(uploadId) {
        await fetch(`${this.apiUrl}/v1/files/uploads/${uploadId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
    }
}

// Usage
const uploader = new MultipartUploader('https://api.example.com', userToken);

try {
    const fileInput = document.querySelector('input[type="file"]');
    const file = fileInput.files[0];

    const result = await uploader.uploadFile(file, 'b3c5…-document-public-id');
    console.log('Upload complete:', result.url);
} catch (error) {
    console.error('Upload failed:', error);
}
```

### Python Example (for testing)

```python
import requests
import math

def upload_file_multipart(api_url, token, file_path, parent_id=None):
    """Upload a file using multipart upload."""

    # 1. Read file info
    with open(file_path, 'rb') as f:
        file_data = f.read()

    file_size = len(file_data)
    file_name = file_path.split('/')[-1]

    # 2. Calculate parts
    part_size = 5 * 1024 * 1024  # 5MB
    num_parts = math.ceil(file_size / part_size)

    # 3. Initiate upload
    headers = {'Authorization': f'Bearer {token}'}
    init_response = requests.post(
        f'{api_url}/v1/files/uploads',
        headers=headers,
        json={
            'file_name': file_name,
            'file_size': file_size,
            'file_content_type': 'application/octet-stream',
            'num_parts': num_parts,
            'part_size': part_size,
            'parent_id': parent_id
        }
    )
    init_data = init_response.json()

    # 4. Upload parts
    parts = []
    for i, presigned_url_data in enumerate(init_data['presigned_urls']):
        start = i * part_size
        end = min(start + part_size, file_size)
        chunk = file_data[start:end]

        # Upload to S3
        part_response = requests.put(
            presigned_url_data['url'],
            data=chunk
        )

        # Extract ETag
        etag = part_response.headers['ETag'].strip('"')

        parts.append({
            'part_number': i + 1,
            'etag': etag
        })

    # 5. Complete upload
    complete_response = requests.post(
        f"{api_url}/v1/files/uploads/{init_data['id']}/complete",
        headers=headers,
        json={'parts': parts}
    )

    return complete_response.json()

# Usage
result = upload_file_multipart(
    'https://api.example.com',
    'your-jwt-token',
    '/path/to/large-file.mp4',
    parent_id='b3c5…-document-public-id'
)
print(f"File uploaded: {result['url']}")
```

## Private Files and Anonymous Uploads

Both are off by default; each project opts in through settings (defaults come from the plugin).

| Setting | Default | |
|---|---|---|
| `BASEAPP_FILES_STORAGE` | `"default"` | `STORAGES` alias that holds uploaded files |
| `BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS` | `False` | Let anonymous callers upload and attach files |
| `BASEAPP_FILES_UPLOAD_TOKEN_MAX_AGE` | `86400` | Lifetime of an anonymous upload token (seconds) |
| `BASEAPP_FILES_ANONYMOUS_MAX_FILE_SIZE` | `None` | Size cap for anonymous uploads (`None`: `MAX_FILE_UPLOAD_SIZE`) |
| `BASEAPP_FILES_ANONYMOUS_UPLOAD_RATE` | `"20/hour"` | DRF throttle rate for anonymous initiations, per IP |
| `BASEAPP_FILES_SIGNED_URL_MAX_AGE` | `3600` | Link lifetime for `SignedFileSystemStorage` |
| `BASEAPP_FILES_UNCLAIMED_ANONYMOUS_MAX_AGE` | `86400` | Age after which unattached anonymous uploads are deleted |
| `BASEAPP_FILES_UPLOAD_TEMP_DIR` | `None` | Parts directory for a storage with no local path (`None`: a private directory in the system temp dir). Use a shared volume when workers run on several hosts |

**Upgrading:** `File.file` now uses the files storage, so a project with its own concrete
`File` model needs `python manage.py makemigrations files` once (a state-only migration).

### Private files

Files are private when the files storage only hands out signed, expiring URLs: an S3 storage
with `querystring_auth`, or `baseapp.files.storage.signed.SignedFileSystemStorage` for local
and non-S3 deployments (its links go through `GET /v1/files/download/{token}`).

```python
STORAGES = {
    **STORAGES,
    "files": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": env("AWS_PRIVATE_STORAGE_BUCKET_NAME"),
            "default_acl": "private",
            "querystring_auth": True,
            "querystring_expire": 3600,
        },
    },
}
BASEAPP_FILES_STORAGE = "files"
```

With private files:
- `url` (GraphQL and REST) is a fresh signed URL, or `null` for viewers without `view_<file>`.
- `file(id:)` / `node(id:)` return `null` for viewers without `view_<file>`.
- `thumbnail` follows the same rules: it is generated into the files storage itself (not the public
  thumbnail storage) and returned as a signed URL, `null` for viewers without `view_<file>`.

Signing alone does not make files private: the objects themselves must not be readable. A system
check refuses to start when a signing S3 storage would still hand out public URLs:
`baseapp_files.E001` for a `custom_domain` without a CloudFront signer (django-storages then
returns unsigned URLs), and `baseapp_files.E002` for a public `default_acl` or
`AWS_S3_OBJECT_PARAMETERS` ACL. Also block public access on the bucket itself.

**Who may upload** is decided before an upload starts, by `add_<file>`: on the target when the
upload names one (`parent_id`, `_can_add_to_target`), otherwise without an object
(`_can_upload`: authenticated users, plus anonymous callers while anonymous uploads are on). A
refusal is a `403 {"detail": "You don't have permission to upload files."}` and nothing is
created. Clients can ask the same question up front with GraphQL `hasPerm(perm: "files.add_file")`.

**Who may attach** files to an object (on upload with `parent_id`, or with `fileAttachToTarget`):
whoever may change it, i.e. `change_<model>` on the target. For a comment that is its author or a
`change_comment` holder, so nobody can add files to someone else's comment. Anonymous attachments
need a target whose rules admit them: override `_can_add_to_target` for those targets.

**Who may view** is decided by `FilesPermissionsBackend`'s `view_<file>` permission. Public
storage: anyone (as before). Private storage: the owner, an anonymous uploader holding the
file's upload token, whoever may view the object the file is attached to (`view_<model>` on
it), and holders of the global `view_<file>` permission. Override `_can_view` (or any other
rule) in your project's backend subclass to change it.

### Anonymous uploads

With `BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS = True`, anonymous callers can initiate uploads
(throttled, optionally size-capped). The response includes an `upload_token`, which proves
ownership since no user owns the file:

- complete / abort: send it as the `X-File-Upload-Token` header;
- `fileAttachToTarget`: pass it in `uploadTokens`. The target must allow files
  (`add_<file>`, which admits anonymous callers while the setting is on; override
  `_can_add_to_target` to restrict which targets accept them).

Anonymous uploads never attached are deleted after `BASEAPP_FILES_UNCLAIMED_ANONYMOUS_MAX_AGE`
by `cleanup_unclaimed_anonymous_files`. It locks and re-checks each file before deleting it, and
attaching locks the same rows, so a file attached meanwhile is kept.

## Protected Downloads

`baseapp.files.downloads` serves **model file fields** (an invoice PDF, a certificate, an
import sheet: any `FileField`/`ImageField`, not only `File`) through the app instead of their
storage URL, and checks the viewer's access **on every request**. Signed storage URLs (above)
let anyone holding the link open the file; a protected download does not.

Nothing changes until a project registers a field: the endpoints are mounted by the files
plugin (or by hand, below) but serve only registered fields.

### Requirements

Registering a field adds a protected way to serve it; it does not close the other ways.

- **Keep the field on private storage**: an S3 bucket with `querystring_auth` and no public
  access, `SignedFileSystemStorage`, an `AliasStorage` naming one of them, or a directory the
  web server does not serve. A field on the default `FileSystemStorage` or a public bucket
  stays readable by anyone at its `MEDIA_URL`/bucket URL. The system check
  `baseapp_files.W010` warns about registered fields whose storage does not sign its URLs;
  silence it (`SILENCED_SYSTEM_CHECKS`) only when the web server denies those URLs.
- **Do not expose the raw field**: leave it out of `DjangoObjectType`s (`fields`/`exclude`)
  and serializers, or replace it there with `ProtectedFileField` /
  `ProtectedFileSerializerField` (below); a plain `FileField` in a payload hands out its
  storage URL. In the admin, use `ProtectedFileAdminMixin`.

### Registering a field

From `AppConfig.ready()`:

```python
from baseapp.files.downloads import Gone, protected_files


def check_not_revoked(user, certificate):
    if certificate.revoked_at:
        raise Gone()


class BillingConfig(AppConfig):
    def ready(self):
        protected_files.register(
            "billing.Invoice",
            "pdf",
            filename=lambda invoice: f"{invoice.number}.pdf",
            ensure=lambda invoice: render_invoice_pdf(invoice),  # missing file: rebuild it
        )
        protected_files.register(
            "events.Certificate",
            "html",
            disposition="inline",
            csp="sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:",
            check=check_not_revoked,
        )
```

| Argument | Default | |
|---|---|---|
| `key` | `"<app>.<model>.<field>"` | Identifies the field in URLs and GraphQL |
| `permission` | `"<app>.view_<model>"` | Checked as `user.has_perm(permission, obj)`; `False` skips it |
| `check` | `None` | `callable(user, obj)` run after the permission. Raise DRF `PermissionDenied` / `NotAuthenticated` / `NotFound` (with your own `code`) or `Gone` (410); they reach the client as they are |
| `queryset` | all objects | `callable(user)`: objects outside it answer 404 instead of 403 |
| `lookup_field` | `"pk"` | What `objectId` matches; `"public_id"` works on `DocumentIdMixin` models |
| `filename` | stored base name | Download name: a `callable(obj)` or a literal |
| `content_type` | allowlisted type of the name | A `callable(obj)` or a literal; unknown types are `application/octet-stream` |
| `disposition` | `"attachment"` | `"inline"` is honoured for types browsers display without running script (images, PDF, audio, video), or when `csp` is given |
| `csp` | `"sandbox; default-src 'none'"` on inline responses | Content-Security-Policy of inline responses |
| `ensure` | `None` | `callable(obj)` returning a `FieldFile`, a file or bytes when nothing is stored, to regenerate or derive the content |
| `cache_control` | `"private, no-store"` | |

**The default permission means "may view the object"**, checked per object with
`user.has_perm("<app>.view_<model>", obj)`. What that grants depends on the authentication
backends: under Django's `ModelBackend` alone, object-level `has_perm` is always `False`, so
only superusers pass; under a BaseApp permission backend it may be broad (`view_profile` is
true for any public profile, for anyone). Being allowed to see an object is often not the same
as being allowed to download its private file, so give each registration its own `permission`
(for example a dedicated `"billing.download_invoice_pdf"` your backend grants) or a `check`,
unless viewing the object is genuinely enough.

A system check reports a registration whose field does not exist (`baseapp_files.E010`), is
not a file field (`E011`), or whose `lookup_field` does not exist (`E012`), and warns when its
storage does not keep files private (`W010`, see Requirements).

Every response carries `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, the
`Cache-Control` above and a `Content-Disposition` whose name is stripped of path components and
control characters. Note that browsers may refuse to display a PDF under a `sandbox` CSP; give
inline PDFs their own `csp` (or serve them as attachments).

### Endpoints

Both live in `baseapp.files.downloads.urls`, a separate include so a project that leaves the
upload API unmounted can mount only these. The files plugin's `v1_urlpatterns` mount them at
`/v1/files/protected/`; elsewhere:

```python
v1_urlpatterns += [re_path(r"^files/protected/", include("baseapp.files.downloads.urls"))]
BASEAPP_FILES_PROTECTED_DOWNLOADS_URL = "/v1/files/protected/"  # where it is mounted
```

- `GET /v1/files/protected/{key}/{objectId}`: for a caller authenticated by the project's
  `DEFAULT_AUTHENTICATION_CLASSES` (JWT, token...) or the session, so admin links work. It
  honours the `Current-Profile` header like `CurrentProfileMixin`. 401 anonymous, 404 unknown
  or outside `queryset`, 403 without access, then whatever `check` raises.
- `GET /v1/files/protected/t/{ticket}`: a **download link**, minted with the GraphQL mutation
  below. The ticket is the only credential, so the link opens natively (a new tab, a download)
  without an `Authorization` header.

Both answer `GET` only: `HEAD` is 405, so link previews and prefetchers that probe with it
neither run `ensure` nor send `protected_file_downloaded`.

### Download links

```graphql
mutation {
  protectedFileLink(input: { key: "billing.invoice.pdf", objectId: "42" }) {
    url        # absolute link to /v1/files/protected/t/{ticket}
    expiresAt
    file { key objectId fileName contentType size }
  }
}
```

`objectId` may also be the object's Relay global id. Access is checked before minting; errors
carry the failure's code (`not_authenticated`, `permission_denied`, `not_found`, `gone`, or
your `check`'s own code).

A ticket is bound to the user who minted it and the profile they were acting as. On every use
the link view reloads the user (who must still be active and have the same password), acts as
that profile while the user may still use it, runs `BASEAPP_FILES_DOWNLOAD_TICKET_USER_CHECK`
and then **re-runs the same access check**, so revoking access takes effect immediately. A
link stops working when it expires, when the file stored at minting is replaced, when the user
is deactivated or changes their password, and when the field is unregistered. A link minted
while nothing was stored (content from `ensure`) keeps working after `ensure` saves a file.
**Logging out does not revoke links**: tickets are stateless, so a link minted before logout
works until it expires. Anyone holding a fresh link can open that one file as the user who
minted it, so keep the lifetime short.

| Setting | Default | |
|---|---|---|
| `BASEAPP_FILES_DOWNLOAD_TICKET_MAX_AGE` | `300` | Link lifetime in seconds |
| `BASEAPP_FILES_DOWNLOAD_TICKET_USER_CHECK` | `None` | `callable(user, request) -> bool` (or its dotted path) that can refuse a link's use, e.g. while a required second factor is missing |
| `BASEAPP_FILES_PROTECTED_DOWNLOADS_URL` | `"/v1/files/protected/"` | Where `baseapp.files.downloads.urls` is mounted |
| `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["protected_download"]` | unset (no limit) | Per-IP rate of the link endpoint, e.g. `"120/hour"` |

### Exposing protected files

Clients never get a URL in a payload; they get a description and mint a link when the user
clicks. The description is null when the field is empty or the viewer may not download it.

```python
from baseapp.files.downloads.graphql import ProtectedFileField
from baseapp.files.downloads.rest_framework import ProtectedFileSerializerField


class InvoiceObjectType(DjangoObjectType):
    pdf = ProtectedFileField("pdf")  # ProtectedFile {key objectId fileName contentType size}


class InvoiceSerializer(serializers.ModelSerializer):
    pdf = ProtectedFileSerializerField()  # {key, object_id, file_name, content_type, size}
```

`size` reads the storage (an S3 `HEAD` per object), so it is only computed when requested in
GraphQL. The mutation is part of `FilesMutations`; projects composing their schema by hand can
add `baseapp.files.downloads.graphql.ProtectedFileMutations`.

### Admin

`ProtectedFileAdminMixin` replaces the upload widget of private file fields with a read-only
`<field>_link`: registered fields link to the authenticated download (the admin session
authenticates it), other private fields show their name only, public fields are unchanged. A
field is private when its storage only signs URLs, or is an `AliasStorage` named in
`private_storage_aliases`.

```python
from baseapp.files.downloads.admin import ProtectedFileAdminMixin


@admin.register(Invoice)
class InvoiceAdmin(ProtectedFileAdminMixin, admin.ModelAdmin):
    private_storage_aliases = ("private",)
```

### Signal and custom views

`baseapp.files.downloads.protected_file_downloaded(sender, instance, field, key, user, request,
via)` is sent after each served `GET` (`via` is `"session"` or `"ticket"`), e.g. to record
access. For content that is not a registered field (say, an email attachment), build the same
hardened response with `protected_content_response(content, filename=..., content_type=...,
disposition=..., csp=...)`, or `protected_file_response(spec, obj, content)` for a spec, after
checking access yourself.

### AliasStorage

`baseapp.files.storage.AliasStorage("private")` is a storage that resolves a `STORAGES` alias on
every operation. Use it on fields whose storage differs per environment (a private bucket in
production, a local directory in development): migrations record the alias rather than a
backend, and `override_settings(STORAGES=...)` takes effect in tests.

```python
pdf = models.FileField(storage=AliasStorage("private"), upload_to="invoices/")
```

## Background Tasks

### Automatic Cleanup of Expired Uploads

Uploads that aren't completed within 24 hours are automatically cleaned up.

#### Setup Celery Beat

The plugin contributes hourly schedules for `cleanup_expired_uploads` and
`cleanup_unclaimed_anonymous_files` (`plugin_registry.get_all_celery_schedules()`). Merge them
into your `settings.py`:

```python
CELERY_BEAT_SCHEDULE = {
    **plugin_registry.get_all_celery_schedules(),
    # your own schedules
}
```

#### What It Does

The cleanup task:
1. Finds files with status "pending" or "uploading" where `upload_expires_at < now()`
2. Aborts the S3 multipart upload (prevents storage charges)
3. Marks the file as "aborted"
4. Clears the `upload_id`

#### Manual Cleanup

You can also run cleanup manually:

```python
from baseapp.files.services.cleanup import cleanup_expired_uploads, cleanup_failed_uploads

# Cleanup expired uploads
cleanup_expired_uploads()

# Cleanup old failed/aborted uploads (older than 7 days)
cleanup_failed_uploads(days_old=7)
```

Or via management command:

```bash
docker compose exec backend python manage.py shell
>>> from baseapp.files.services.cleanup import cleanup_expired_uploads
>>> cleanup_expired_uploads()
```

## Troubleshooting

### "Part size must be at least 5MB"

**Problem:** S3 requires multipart uploads to have parts of at least 5MB (except the last part).

**Solution:**
- Use `part_size >= 5242880` (5MB) for files larger than 5MB
- For files smaller than 5MB, use `num_parts = 1` and set `part_size = file_size`

### "CORS policy" errors when uploading to S3

**Problem:** Browser blocks S3 upload due to CORS restrictions.

**Solution:** Configure CORS on your S3 bucket (see [Configuration](#4-s3-bucket-configuration) above).

### ETags don't match / Upload completion fails

**Problem:** ETags sent to complete endpoint don't match S3's records.

**Solution:**
- Ensure you're extracting ETags from S3 response headers correctly
- Remove quotes from ETags: `etag.replace(/"/g, '')`
- Upload parts in the correct order (part 1, 2, 3...)
- Don't modify file chunks before uploading

### Uploads stuck in "uploading" status

**Problem:** Client uploaded parts but never called complete endpoint.

**Solution:**
- Ensure your client code calls the complete endpoint
- Check for JavaScript errors during upload
- Abandoned uploads are automatically cleaned up after 24 hours

### "File size doesn't match parts"

**Problem:** The validation `(num_parts - 1) * part_size <= file_size <= num_parts * part_size` failed.

**Solution:**
```javascript
// Correct calculation
const partSize = 5 * 1024 * 1024; // 5MB
const numParts = Math.ceil(fileSize / partSize);

// Incorrect - don't round down!
const numParts = Math.floor(fileSize / partSize); // ❌ Wrong
```

### Local storage fallback not working

**Problem:** Getting S3 errors in development.

**Solution:**
- Local fallback only works if NOT using S3Boto3Storage
- Check the files storage in Django shell:
  ```python
  from baseapp.files.storage import files_storage
  print(files_storage.__class__)
  # Should NOT be S3Boto3Storage for local fallback
  ```

## Advanced Topics

### Storage Folder

Files are stored under `files/` in the files storage. To partition them, e.g. per tenant or per
parent object, override `get_upload_folder` on your concrete `File` model:

```python
class File(AbstractFile):
    def get_upload_folder(self) -> str:
        target = self.parent.content_object if self.parent_id else None
        tenant = getattr(target, "tenant", None)
        return f"tenants/{tenant.public_id}" if tenant else "files"
```

The folder is read when an upload starts, and the resulting name is kept in `upload_storage_name`,
so an upload completes in the same place even if the folder would change meanwhile. A file saved
directly (`File.objects.create(file=...)`) goes through `File.file`'s `upload_to`, which reads the
same folder; its stored name is `file.name`, and `upload_storage_name` stays empty because there is
no upload to complete. Use identifiers that are not personal data: the folder is part of the object
key and of S3 URLs. The folder must be a plain relative path, and the whole storage name must fit
the model's fields (512 characters); `.` and `..` segments, empty segments (`a//b`), backslashes
and over-long names are rejected, and an upload whose name is rejected is refused with nothing
recorded.

**Upgrading:** this adds `upload_storage_name` and changes `File.file`'s `upload_to`, so a project
with its own concrete `File` model needs `python manage.py makemigrations files` once. Uploads
already in progress when you deploy have no stored name and complete where they always would.

### Custom Storage Backends

You can add support for other storage backends (GCS, Azure, etc.) by:

1. Create a new handler in `baseapp/files/storage/`:

```python
# baseapp/files/storage/gcs.py
from .base import BaseUploadHandler

class GCSMultipartUploadHandler(BaseUploadHandler):
    def supports_multipart(self) -> bool:
        return True

    # Implement other methods...
```

2. Update the factory in `baseapp/files/storage/__init__.py`:

```python
def get_upload_handler():
    storage_class = type(default_storage)

    if "S3Boto3Storage" in str(storage_class):
        from .s3 import S3MultipartUploadHandler
        return S3MultipartUploadHandler()
    elif "GoogleCloudStorage" in str(storage_class):
        from .gcs import GCSMultipartUploadHandler
        return GCSMultipartUploadHandler()
    else:
        from .local import LocalUploadHandler
        return LocalUploadHandler()
```

### Resumable Uploads (not planned)

Resuming interrupted uploads across sessions is intentionally **out of scope** — the
package provides multipart upload for large files only. If an upload is interrupted,
the client aborts (or lets the expiration cleanup task abort) and re-initiates.
Clients may still pause/resume within a session by holding on to the presigned URLs
returned at initiation, uploading only the remaining parts while the URLs are valid.

### File Size Quotas

Add per-user file size quotas:

```python
# In UploadService._validate_file_params
def _validate_file_params(self, file_size, num_parts, part_size, user):
    # Existing validation...

    # Check user quota
    user_total = File.objects.filter(
        created_by=user,
        upload_status='completed'
    ).aggregate(total=Sum('file_size'))['total'] or 0

    user_quota = getattr(settings, 'FILE_UPLOAD_QUOTA_PER_USER', 10 * 1024 * 1024 * 1024)  # 10GB

    if user_total + file_size > user_quota:
        raise ValueError(f"Upload would exceed your quota of {user_quota} bytes")
```

### File Type Restrictions

Only extensions on an allowlist can be uploaded (`baseapp/files/content_safety.py`). The
default covers common media, documents and archives:

- Images: `.jpg .jpeg .png .gif .webp .avif .heic .heif .bmp .tif .tiff`
- Video: `.mp4 .m4v .mov .webm .mkv .avi .3gp`
- Audio: `.mp3 .m4a .aac .wav .ogg .oga .opus .flac`
- Documents: `.pdf .doc .docx .xls .xlsx .ppt .pptx .odt .ods .odp .rtf .txt .csv`
- Archives: `.zip .7z .rar .tar .gz`

Anything else is rejected when the upload starts:

```json
400 {"file_name": ["Files of type .html are not allowed."]}
```

The list maps each extension to the content type the file is **stored and served with**; the
type the client declares is ignored. Otherwise `photo.png` declared as `text/html` would be
served as a page and run script on the site's domain (stored XSS), even from an S3 bucket
behind a subdomain.

On S3, files a browser would not display safely (everything but common images, video, audio
and PDF) are stored with `Content-Disposition: attachment`, so opening them downloads rather
than renders them. Embedded images and video still display.

Replace or extend the list per project:

```python
from baseapp.files.content_safety import DEFAULT_ALLOWED_FILE_TYPES

# Extend: keep the defaults and add more types.
BASEAPP_FILES_ALLOWED_FILE_TYPES = {
    **DEFAULT_ALLOWED_FILE_TYPES,
    ".dwg": "application/acad",
}

# Or replace: a list of extensions takes each type from `mimetypes`.
BASEAPP_FILES_ALLOWED_FILE_TYPES = [".jpg", ".png", ".pdf"]
```

Avoid allowing `.svg`, `.html`, `.xml` or `.js`: browsers run them as pages, and where media is
served from the site's own domain (local storage, nginx `/media/`) that is stored XSS.

### Progress Notifications

Add real-time progress updates via WebSockets:

```python
# When parts are uploaded (would need additional endpoint)
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def notify_upload_progress(file_id, uploaded_parts, total_parts):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'upload_{file_id}',
        {
            'type': 'upload_progress',
            'uploaded': uploaded_parts,
            'total': total_parts,
            'progress': (uploaded_parts / total_parts) * 100
        }
    )
```

### Parallel Part Uploads

The API supports parallel part uploads out of the box. Example:

```javascript
// Upload all parts in parallel
const uploadPromises = presigned_urls.map(async (urlData, index) => {
    const start = index * partSize;
    const end = Math.min(start + partSize, file.size);
    const chunk = file.slice(start, end);

    const response = await fetch(urlData.url, {
        method: 'PUT',
        body: chunk
    });

    return {
        part_number: index + 1,
        etag: response.headers.get('ETag').replace(/"/g, '')
    };
});

const parts = await Promise.all(uploadPromises);
```

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review API error responses (they include detailed error messages)
3. Check Django logs for server-side errors
4. Verify S3 bucket permissions and CORS configuration
