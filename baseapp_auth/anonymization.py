import swapper
from django.db import connection


def anonymize_activitylog(self, *args, **kwargs):
    """
     Ensures full anonymization of user-related activity logs.

     The pghistory_context table stores historical context for model changes,
     including references to user and profile information in its metadata JSONB column.
     Simply deleting or anonymizing the user object does not remove these references
     from historical records.

     This method directly updates the metadata fields for 'user' and 'profile' to null,
     guaranteeing that no personal identifiers remain in the activity log context.
     This is essential for compliance with privacy regulations and user data deletion requests.

    IMPORTANT: Even after anonymization, some metadata may still contain user-related information,
     but these are retained strictly for audit purposes. Useful audit metadata includes timestamps,
     action types (verb), object/resource IDs, system or user role (without personal identifiers),
     IP addresses (if not considered personal data), and details of changes made. Personal identifiers
     such as names, emails, and profile information are removed or set to null.
    """
    ActivityLog = swapper.load_model("baseapp_activity_log", "ActivityLog")
    all_activity_logs = ActivityLog.objects.filter(user=self)
    if all_activity_logs.exists():
        user_id_str = str(self.id)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pghistory_context
                SET metadata = jsonb_set(
                    jsonb_set(
                        metadata,
                        '{user}', 'null', true
                    ),
                    '{profile}', 'null', true
                )
                WHERE metadata->>'user' = %s
            """,
                [user_id_str],
            )
