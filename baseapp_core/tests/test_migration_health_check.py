import json

from django.apps import apps
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.autodetector import Migration, MigrationAutodetector
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.operations.base import Operation
from django.db.migrations.state import ProjectState
from django.db.models import Field
from django.db.models.indexes import Index
from django.test import TestCase


class MigrationJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Field):  # django field
            return "__cant_serialize__"
        if isinstance(obj, Migration) or isinstance(obj, Operation) or isinstance(obj, Index):
            return obj.__dict__
        if isinstance(obj, set):
            return list(obj)
        try:
            return super().default(obj)
        except (ValueError, TypeError):
            return f"__cant_serialize__ instance of {obj.__class__}"


class TestMigrationHealthCheck(TestCase):
    """
    Try to pre-empt migration woes.
    """

    def migration_progress_callback(*args, **kwargs):
        # This is a no-op to keep the MigrationExecutor's
        # constructor happy
        pass

    def test_for_uncreated_migrations(self):
        """
        Migrations are created and added to the repo, so the CI detects if any
        migrations were created but not pushed to the git branch.
        """

        connection = connections[DEFAULT_DB_ALIAS]

        # Work out which apps have migrations and which do not
        executor = MigrationExecutor(connection, self.migration_progress_callback)

        autodetector = MigrationAutodetector(
            executor.loader.project_state(), ProjectState.from_apps(apps)
        )
        changes = autodetector.changes(graph=executor.loader.graph)
        changes.pop("avatar", None)  # out of our control
        changes.pop("silk", None)  # out of our control

        if changes:
            migrations_missing = json.dumps(changes, indent=4, cls=MigrationJSONEncoder)
            self.fail(
                "Your models have changes that are not yet reflected "
                "in a migration. You should add them now. "
                "Relevant app(s): %s\n"
                "Migrations missing:\n%s" % (changes.keys(), migrations_missing)
            )
