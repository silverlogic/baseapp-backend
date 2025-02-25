from django.db import migrations

from baseapp_core.swappable import get_apps_model


def create_default_report_types_and_transfer_values(apps, schema_editor):
    ReportType = get_apps_model(apps, "baseapp_reports", "ReportType")
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    ContentType = apps.get_model("contenttypes", "ContentType")
    comment_content_type = ContentType.objects.get(app_label="comments", model="comment")
    page_content_type = ContentType.objects.get(app_label="pages", model="page")

    ReportType.objects.bulk_create(
        [
            ReportType(name="spam", label="Spam", content_type=[comment_content_type]),
            ReportType(name="inappropriate", label="Inappropriate", content_type=[comment_content_type]),
            ReportType(name="fake", label="Fake", content_type=[comment_content_type]),
            ReportType(name="other", label="Other", content_type=[comment_content_type, page_content_type]),
            ReportType(name="scam", label="Scam or fraud", content_type=[comment_content_type]),
            ReportType(name="adult_content", label="Adult Content", content_type=[page_content_type]),
            ReportType(name="violence", label="Violence, hate or exploitation", content_type=[page_content_type]),
            ReportType(name="bulling", label="Bulling or unwanted contact", content_type=[page_content_type]),
        ]
    )
    adult_content = ReportType.objects.filter(name="adult_content").first()
    if not adult_content:
        raise ValueError("adult_content ReportType was not created!")
    ReportType.objects.bulk_create(
        [
            ReportType(name="pornography", label="Pornography", parent_type=adult_content, content_type=[page_content_type]),
            ReportType(name="childAbuse", label="Child abuse", parent_type=adult_content, content_type=[page_content_type]),
            ReportType(name="prostituition", label="Prostituition", parent_type=adult_content, content_type=[page_content_type]),
        ]
    )

    for report in Report.objects.all():
        report_type = ReportType.objects.filter(name=report.report_type).first()
        report.report_type_fk = report_type
        report.save()

def reverse_create_default_report_types(apps, schema_editor):
    ReportType = get_apps_model(apps, "baseapp_reports", "ReportType")
    Report = get_apps_model(apps, "baseapp_reports", "Report")

    ReportType.objects.all().delete()

    for report in Report.objects.all():
        report.report_type_fk = None
        report.save()


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_reports", "0004_alter_report_report_type_reporttype"),
    ]

    operations = [
        migrations.RunPython(create_default_report_types_and_transfer_values, reverse_create_default_report_types),
    ]
