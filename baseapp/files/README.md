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
- Storage factory checks if `default_storage` is `S3Boto3Storage`
- If not S3, uses `LocalUploadHandler` automatically
- Local handler stores parts in `MEDIA_ROOT/temp_uploads/`
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
    "parent_content_type": "testapp.post",  // optional
    "parent_object_id": 123                  // optional
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
    "parent_content_type": 23,
    "parent_object_id": 123
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
    "parent_content_type": "testapp.comment",
    "parent_object_id": 789
}
```

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
- `parent_content_type` (string, optional) - e.g., "testapp.post"
- `parent_object_id` (integer, optional) - ID of parent object

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
- `parent_content_type` (string, optional) - Filter by parent type
- `parent_object_id` (integer, optional) - Filter by parent ID

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
- `parent_content_type` (string, required) - e.g., "testapp.post"
- `parent_object_id` (integer, required) - Parent object ID

## Client Implementation

### JavaScript Example (Complete Flow)

```javascript
class MultipartUploader {
    constructor(apiUrl, token) {
        this.apiUrl = apiUrl;
        this.token = token;
    }

    async uploadFile(file, parentContentType = null, parentObjectId = null) {
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
                parent_content_type: parentContentType,
                parent_object_id: parentObjectId
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

    const result = await uploader.uploadFile(file, 'testapp.post', 123);
    console.log('Upload complete:', result.url);
} catch (error) {
    console.error('Upload failed:', error);
}
```

### Python Example (for testing)

```python
import requests
import math

def upload_file_multipart(api_url, token, file_path, parent_content_type=None, parent_object_id=None):
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
            'parent_content_type': parent_content_type,
            'parent_object_id': parent_object_id
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
    parent_content_type='testapp.post',
    parent_object_id=123
)
print(f"File uploaded: {result['url']}")
```

## Background Tasks

### Automatic Cleanup of Expired Uploads

Uploads that aren't completed within 24 hours are automatically cleaned up.

#### Setup Celery Beat

Add to your `settings.py`:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-uploads': {
        'task': 'baseapp.files.services.cleanup.cleanup_expired_uploads',
        'schedule': crontab(minute=0),  # Run every hour
    },
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
- Check `default_storage` in Django shell:
  ```python
  from django.core.files.storage import default_storage
  print(type(default_storage))
  # Should NOT be S3Boto3Storage for local fallback
  ```

## Advanced Topics

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

### Resumable Uploads

The current implementation doesn't support resuming interrupted uploads. To add this:

1. Client should track which parts were successfully uploaded
2. Add an endpoint to query uploaded parts:
   ```python
   @action(detail=True, methods=['get'])
   def uploaded_parts(self, request, pk=None):
       file_obj = self.get_object()
       # Return list of uploaded part numbers
       return Response(file_obj.uploaded_parts or {})
   ```
3. Client resumes by only uploading missing parts

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

Restrict allowed file types:

```python
# In settings.py
ALLOWED_FILE_TYPES = [
    'image/jpeg',
    'image/png',
    'video/mp4',
    'application/pdf',
]

# In InitiateUploadSerializer.validate_file_content_type
def validate_file_content_type(self, value):
    allowed = getattr(settings, 'ALLOWED_FILE_TYPES', None)
    if allowed and value not in allowed:
        raise serializers.ValidationError(
            f"File type {value} not allowed. Allowed types: {', '.join(allowed)}"
        )
    return value
```

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
