Needs to add to settings:
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "tus-resumable",
    "upload-length",
    "upload-metadata",
    "upload-creator"
]

# To Do

- signals to delete video from cloudflare once model is deleted
- global task to update video status?
- webhook?


