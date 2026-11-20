from django.dispatch import Signal

# Sent after a protected file response has been built, once access was granted.
#
# sender:   the registered model class
# instance: the object whose file was served
# field:    the field name
# key:      the registry key
# user:     the user the download was served to (AnonymousUser when allowed anonymously)
# request:  the HTTP request
# via:      "session" (authenticated GET) or "ticket" (download link)
protected_file_downloaded = Signal()
