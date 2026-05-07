from io import StringIO
from unittest.mock import patch

import pytest
import swapper
from django.core.management import call_command

from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ReportFactory, ReportTypeFactory

Report = swapper.load_model("baseapp_reports", "Report")
ReportableMetadata = swapper.load_model("baseapp_reports", "ReportableMetadata")

pytestmark = pytest.mark.django_db


def _call():
    """Run the command and return its captured stdout."""
    out = StringIO()
    call_command("update_reports_count", stdout=out)
    return out.getvalue()


def test_command_recomputes_metadata_from_existing_reports():
    """Even if metadata rows are stale (or missing), the command should produce counts
    that match the live `Report` data."""
    target = ProfileFactory()
    spam = ReportTypeFactory(key="spam_cmd_a", label="Spam A")
    fake = ReportTypeFactory(key="fake_cmd_a", label="Fake A")

    ReportFactory(target=target, report_type=spam)
    ReportFactory(target=target, report_type=spam)
    ReportFactory(target=target, report_type=fake)

    metadata = ReportableMetadata.get_for_object(target)
    metadata.reports_count = {"total": 0}
    metadata.save(update_fields=["reports_count"])

    output = _call()

    metadata.refresh_from_db()
    assert metadata.reports_count["spam_cmd_a"] == 2
    assert metadata.reports_count["fake_cmd_a"] == 1
    assert metadata.reports_count["total"] == 3
    assert "Refreshed 1 reportable target" in output


def test_command_iterates_over_distinct_targets_only():
    """A target with multiple reports should only get refreshed once. The command's
    summary counts distinct `target_document` references, not raw report rows."""
    target_a = ProfileFactory()
    target_b = ProfileFactory()
    rt = ReportTypeFactory(key="other_cmd_a", label="Other A")

    ReportFactory(target=target_a, report_type=rt)
    ReportFactory(target=target_a, report_type=rt)
    ReportFactory(target=target_b, report_type=rt)

    output = _call()

    assert "Refreshed 2 reportable target(s)" in output
    assert ReportableMetadata.get_for_object(target_a).reports_count["total"] == 2
    assert ReportableMetadata.get_for_object(target_b).reports_count["total"] == 1


def test_command_no_op_when_no_reports():
    """With no `Report` rows in the DB the command exits cleanly and reports zero
    refreshed targets — exercises the fresh-DB / first-run scenario."""
    output = _call()
    assert "Refreshed 0 reportable target(s)" in output


def test_command_skips_targets_when_content_object_is_missing():
    """If a `DocumentId`'s `content_object` resolves to `None` (e.g. the
    underlying row was hard-deleted out from under the document), the command should
    skip that target rather than crash. We exercise the defensive branch by patching
    `DocumentId.content_object` to return `None` for every row — each iteration
    falls into `continue`."""
    target = ProfileFactory()
    rt = ReportTypeFactory(key="violence_cmd", label="Violence cmd")
    ReportFactory(target=target, report_type=rt)

    with patch(
        "baseapp_core.models.DocumentId.content_object",
        new_callable=lambda: property(lambda self: None),
    ):
        output = _call()

    # The defensive `continue` branch fires: 0 targets refreshed, no exception leaks.
    assert "Refreshed 0 reportable target(s)" in output
