"""
Django signals for cross-package events.

All runtime event communication uses these signals. Receivers are connected
in AppConfig.ready(); no entry points are used.
"""

from django.dispatch import Signal

# Emitted when a new DocumentId row is created (Python path or post_save).
# Kwargs: document_id (int)
document_created = Signal()
