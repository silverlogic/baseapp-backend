from django.apps import apps
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState
from django.test import TestCase


class TestMigrationHealthCheck(TestCase):
    """
    Try to pre-empt migration woes.
    """
    def migration_progress_callback(*args, **kwargs):
        # This is a no-op to keep the MigrationExecutor's
        # constructor happy
        pass

    def test_for_uncreated_migrations(self):

        connection = connections[DEFAULT_DB_ALIAS]

        # Work out which apps have migrations and which do not
        executor = MigrationExecutor(
            connection,
            self.migration_progress_callback
        )

        autodetector = MigrationAutodetector(
            executor.loader.project_state(),
            ProjectState.from_apps(apps),
        )
        changes = autodetector.changes(graph=executor.loader.graph)
        if changes:
            self.fail(
                "Your models have changes that are not yet reflected "
                "in a migration. You should add them now. "
                "Relevant app(s): %s" % changes.keys()
            )
