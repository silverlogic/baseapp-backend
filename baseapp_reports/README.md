# BaseApp Reports

Reusable app that lets users report any model, customisable for the project's needs.

## How to install

```bash
pip install baseapp-backend
```

Add `baseapp_reports` to `INSTALLED_APPS`. The package registers itself as a plugin
(see `baseapp_reports.plugin:ReportsPlugin`), so:

- `ReportsQueries` / `ReportsMutations` are contributed via
  `plugin_registry.get_all_graphql_queries()` / `get_all_graphql_mutations()`.
- `ReportsPermissionsBackend` is contributed via
  `plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_reports")`.
- The `ReportsInterface` GraphQL interface is registered by name; consumers fetch
  it from `graphql_shared_interfaces` instead of importing it directly.
- A `reportable_metadata` shared service exposes `get_reports_count(obj)` and
  `annotate_queryset(qs)` for any object with a `DocumentId`. Consumers should
  use this service instead of inheriting from a mixin.

## How to use

### GraphQL — opt a type into reports

Request the interface by name in your object type's `Meta.interfaces`:

```python
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class UserNode(DjangoObjectType):
    class Meta:
        interfaces = graphql_shared_interfaces.get(RelayNode, "ReportsInterface")
```

When `baseapp_reports` is installed the registry returns the real
`ReportsInterface`; when it is not, the call falls back to the defaults so the
type still works.

### GraphQL — exposing the schema

Nothing to do. The plugin entry-point in `pyproject.toml` registers
`ReportsQueries` and `ReportsMutations`, and the project's root `Query` /
`Mutation` should already spread `*plugin_registry.get_all_graphql_queries()`
and `*plugin_registry.get_all_graphql_mutations()`. `reportCreate` and
`allReportTypes` show up automatically.

### Reporting counts on a model

Reports counts are stored in `ReportableMetadata` (one row per `DocumentId`),
not on the reportable model itself. Read counts via the shared service:

```python
from baseapp_core.plugins import shared_services


service = shared_services.get("reportable_metadata")
reports_count = service.get_reports_count(my_obj)  # dict like {"total": 0, "spam": 0, ...}
```

For querysets that will resolve `reportsCount` for many rows, annotate up front to
avoid N+1:

```python
qs = service.annotate_queryset(qs)
```

The `Report.save()` / `Report.delete()` hooks already maintain
`ReportableMetadata.reports_count` for you whenever a report is added or
removed.

## How to customise the Report model

Define a concrete model that subclasses the abstracts in your project:

```python
# myproject/reports/models.py
from baseapp_reports.models import (
    AbstractReport,
    AbstractReportType,
    AbstractReportableMetadata,
)


class ReportType(AbstractReportType):
    class Meta(AbstractReportType.Meta):
        pass


class Report(AbstractReport):
    class Meta(AbstractReport.Meta):
        pass


class ReportableMetadata(AbstractReportableMetadata):
    class Meta(AbstractReportableMetadata.Meta):
        pass
```

Add the new app to `INSTALLED_APPS`, run `makemigrations` / `migrate`, and point
the swapper settings at it:

```python
# settings.py
BASEAPP_REPORTS_REPORT_MODEL = "reports.Report"
BASEAPP_REPORTS_REPORTTYPE_MODEL = "reports.ReportType"
BASEAPP_REPORTS_REPORTABLEMETADATA_MODEL = "reports.ReportableMetadata"
```

## Writing test cases in your project

`AbstractReportFactory` helps you build factories for the swapped Report model:

```python
import factory
from baseapp_reports.tests.factories import AbstractReportFactory


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "comments.Comment"


class CommentReportFactory(AbstractReportFactory):
    target = factory.SubFactory(CommentFactory)

    class Meta:
        model = "reports.Report"  # or "baseapp_reports.Report" if you didn't swap
```

## Migrating an existing project to ReportableMetadata

Older projects inherited a `ReportableModel` mixin that added a `reports_count`
JSONField directly on the reportable model. That mixin has been removed. To
migrate:

1. Add a migration that creates the `ReportableMetadata` table for your project
   (mirror `baseapp_reports/migrations/0007_reportablemetadata.py`).
2. Add a follow-up migration that calls
   `migrate_legacy_reports_count_to_metadata(...)` from
   `baseapp_reports.migration_helpers.convert_legacy_reports_count_to_metadata_helper`,
   passing your reportable model's app label and name. After the data is moved,
   `RemoveField` the legacy `reports_count` column.

   If that app must also run with `baseapp_reports` uninstalled, keep the
   migration graph optional: make the `("reports", "…reportablemetadata")`
   dependency conditional (only add it when `"reports" in apps.app_configs`) and
   guard the backfill (`apps.get_model("reports", "ReportableMetadata")` inside a
   `try/except LookupError` that returns early). The `RemoveField` /
   trigger-regen operations touch your own table, so they stay unconditional.
3. Optionally re-seed any drift with
   `seed_reportable_metadata_from_reports(...)` from
   `baseapp_reports.migration_helpers.seed_reportable_metadata_from_reports_helper`.

## How to develop

Clone the monorepo into your backend directory:

```bash
git clone git@github.com:silverlogic/baseapp-backend.git
```

Then install editable:

```bash
pip install -e baseapp-backend
```
