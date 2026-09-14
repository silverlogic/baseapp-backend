import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ReportFactory, ReportTypeFactory

Report = swapper.load_model("baseapp_reports", "Report")
ReportableMetadata = swapper.load_model("baseapp_reports", "ReportableMetadata")

pytestmark = pytest.mark.django_db


def test_report_save_creates_metadata_and_increments_count() -> None:
    """Creating a Report through the ORM should populate ReportableMetadata for the target
    and increment `reports_count[type.key]` and `reports_count["total"]`."""
    target = ProfileFactory()
    report_type = ReportTypeFactory(key="spam_test", label="Spam test")

    ReportFactory(target=target, report_type=report_type)

    metadata = ReportableMetadata.get_for_object(target)
    assert metadata is not None
    assert metadata.reports_count["spam_test"] == 1
    assert metadata.reports_count["total"] == 1


def test_report_delete_decrements_count() -> None:
    """Deleting a Report should reduce both the per-type and total counters."""
    target = ProfileFactory()
    report_type = ReportTypeFactory(key="fake_test", label="Fake test")

    report_a = ReportFactory(target=target, report_type=report_type)
    report_b = ReportFactory(target=target, report_type=report_type)

    metadata = ReportableMetadata.get_for_object(target)
    assert metadata.reports_count["fake_test"] == 2
    assert metadata.reports_count["total"] == 2

    report_a.delete()

    metadata.refresh_from_db()
    assert metadata.reports_count["fake_test"] == 1
    assert metadata.reports_count["total"] == 1

    report_b.delete()

    metadata.refresh_from_db()
    assert metadata.reports_count["fake_test"] == 0
    assert metadata.reports_count["total"] == 0


def test_reports_count_buckets_per_report_type() -> None:
    """Reports against the same target with different `ReportType` keys should land in
    different buckets, with the total reflecting the sum."""
    target = ProfileFactory()
    spam_type = ReportTypeFactory(key="spam_b", label="Spam B")
    scam_type = ReportTypeFactory(key="scam_b", label="Scam B")

    ReportFactory(target=target, report_type=spam_type)
    ReportFactory(target=target, report_type=spam_type)
    ReportFactory(target=target, report_type=scam_type)

    metadata = ReportableMetadata.get_for_object(target)
    assert metadata.reports_count["spam_b"] == 2
    assert metadata.reports_count["scam_b"] == 1
    assert metadata.reports_count["total"] == 3


def test_reports_count_isolated_per_target() -> None:
    """Reports against profile A must not bleed into profile B's metadata."""
    target_a = ProfileFactory()
    target_b = ProfileFactory()
    report_type = ReportTypeFactory(key="other_b", label="Other B")

    ReportFactory(target=target_a, report_type=report_type)

    metadata_a = ReportableMetadata.get_for_object(target_a)
    metadata_b = ReportableMetadata.get_for_object(target_b)

    assert metadata_a.reports_count["total"] == 1
    assert metadata_b is None or metadata_b.reports_count["total"] == 0


def test_update_reports_count_recomputes_from_existing_reports(django_user_client) -> None:
    """Calling `Report.update_reports_count(target)` directly should recompute counters
    from the live `Report` rows even if the metadata row is out of sync."""
    target = ProfileFactory()
    report_type = ReportTypeFactory(key="recount", label="Recount")

    report = ReportFactory(target=target, report_type=report_type)

    metadata = ReportableMetadata.get_for_object(target)
    metadata.reports_count = {"total": 0, "recount": 0}
    metadata.save(update_fields=["reports_count"])

    Report.update_reports_count(target)

    metadata.refresh_from_db()
    assert metadata.reports_count["recount"] == 1
    assert metadata.reports_count["total"] == 1

    # Sanity: the report row really is the one we created.
    assert report.pk == Report.objects.get(target_document_id=metadata.target_id).pk


def test_update_reports_count_no_op_when_target_is_none() -> None:
    """`update_reports_count(None)` should silently no-op rather than crash."""
    Report.update_reports_count(None)  # should not raise
