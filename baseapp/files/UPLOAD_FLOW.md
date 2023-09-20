# File Upload Flow

## Overview

The file upload system supports both direct S3 uploads (production) and local storage uploads (dev/test) with multipart upload capabilities.

## Multipart Upload Workflow

### 1. Initiate Upload
**POST** `/v1/files/uploads/`

```json
{
  "file_name": "large-video.mp4",
  "file_size": 104857600,
  "file_content_type": "video/mp4",
  "num_parts": 20,
  "part_size": 5242880,
  "parent_content_type": "testapp.post",  // optional
  "parent_object_id": 123  // optional
}
```

**Response:**
```json
{
  "file_obj": {
    "id": "7",
    "file_name": "large-video.mp4",
    "upload_status": "uploading"
  },
  "upload_id": "abc-123-def-456",
  "presigned_urls": [
    {
      "part_number": 1,
      "url": "https://s3.amazonaws.com/...",  // or local endpoint
      "method": "PUT"
    },
    ...
  ],
  "expires_in": 3600
}
```

### 2. Upload Parts

#### For S3 (Production)
Upload directly to the presigned URLs:
```bash
PUT https://s3.amazonaws.com/bucket/path?uploadId=...&partNumber=1
Content-Type: application/octet-stream
Body: <binary data>
```

#### For Local Storage (Dev/Test)
**PUT** `/v1/files/presigned-uploads/{file_id}/upload-part/{part_number}/?token=<signed_token>`

The presigned URLs returned from the initiate endpoint include a signed token for authentication.

```bash
PUT /v1/files/presigned-uploads/7/upload-part/1/?token=<signed_token>
Content-Type: application/octet-stream
Body: <binary data>
```

**Response:**
```json
{
  "part_number": 1,
  "etag": "abc123def456..."
}
```

**Response Headers:**
```
ETag: abc123def456...
```

**Note:** The token is generated using Django signing and is valid for 1 hour. No session authentication or CSRF protection is required for this endpoint. The ETag is returned both in the response body and as an HTTP header for S3 compatibility.

### 3. Complete Upload
**POST** `/v1/files/uploads/{id}/complete/`

```json
{
  "parts": [
    {"part_number": 1, "etag": "abc123..."},
    {"part_number": 2, "etag": "def456..."},
    ...
  ]
}
```

**Response:**
```json
{
  "id": "7",
  "file_name": "large-video.mp4",
  "file_size": 104857600,
  "file_content_type": "video/mp4",
  "upload_status": "completed",
  "url": "https://cdn.example.com/files/...",
  "created": "2025-01-01T12:00:00Z"
}
```

### 4. Abort Upload (Optional)
**DELETE** `/v1/files/uploads/{id}/`

Cancels the upload and cleans up temporary files.

## Storage Handlers

### S3 (Production)
- Generates real presigned URLs pointing to S3
- Client uploads directly to S3
- No backend bandwidth used for file data
- Supports true multipart uploads

### Local (Dev/Test)
- Generates "presigned URLs" with signed tokens pointing to backend endpoint
- Client uploads to backend via `/presigned-uploads/{id}/upload-part/{part_number}/` endpoint
- Token authentication using Django signing (no session auth or CSRF required)
- Backend stores parts in temp directory
- On complete, parts are concatenated into final file

## Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/files/uploads/` | Initiate multipart upload |
| PUT | `/v1/files/presigned-uploads/{id}/upload-part/{part_number}/?token=...` | Upload a single part (local storage, token-authenticated) |
| POST | `/v1/files/uploads/{id}/complete/` | Complete the upload |
| DELETE | `/v1/files/uploads/{id}/` | Abort the upload |
| GET | `/v1/files/` | List files |
| GET | `/v1/files/{id}/` | Get file details |
| PATCH | `/v1/files/{id}/` | Update file metadata |
| DELETE | `/v1/files/{id}/` | Delete file |

## Configuration

### Settings
```python
# Maximum file size (default: 5GB)
MAX_FILE_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024

# Storage backend
UPLOAD_STORAGE_HANDLER = "local"  # or "s3"
```

### Local Storage
```python
UPLOAD_STORAGE_HANDLER = "local"
```
- Uses `LocalUploadHandler`
- Stores files in `MEDIA_ROOT/files/`
- Temp parts in `MEDIA_ROOT/temp_uploads/{upload_id}/`

### S3 Storage
```python
UPLOAD_STORAGE_HANDLER = "s3"
AWS_ACCESS_KEY_ID = "..."
AWS_SECRET_ACCESS_KEY = "..."
AWS_STORAGE_BUCKET_NAME = "my-bucket"
AWS_S3_REGION_NAME = "us-east-1"
```
- Uses `S3UploadHandler`
- Generates presigned URLs for direct S3 upload
- No backend file handling

## Error Handling

### Common Errors
- **400 Bad Request**: Invalid parameters, part numbers, or file size
- **403 Forbidden**: User doesn't own the file/upload
- **404 Not Found**: File or upload not found
- **413 Payload Too Large**: File exceeds `MAX_FILE_UPLOAD_SIZE`

### Upload Status
- `pending`: Upload initiated but not started
- `uploading`: Parts being uploaded
- `completed`: Upload finished successfully
- `failed`: Upload failed (error during completion)
- `aborted`: Upload cancelled by user

## Best Practices

1. **Chunk Size**: Use 5MB minimum for parts (S3 requirement)
2. **Part Count**: Keep between 1-10,000 parts
3. **Error Handling**: Always store ETags from part uploads
4. **Cleanup**: Call abort endpoint if upload fails
5. **Expiration**: Complete uploads within 24 hours (tokens expire in 1 hour)
6. **Local Dev**: Use the presigned URLs with tokens returned from the initiate endpoint
