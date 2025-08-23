import swapper
from django.db import connection


def anonymize_activitylog(self, *args, **kwargs):
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
