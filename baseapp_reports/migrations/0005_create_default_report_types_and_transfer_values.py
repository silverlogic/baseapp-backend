from django.db import migrations

from baseapp_core.swappable import get_apps_model


def create_default_report_types_and_transfer_values(apps, schema_editor):
    ReportType = get_apps_model(apps, "baseapp_reports", "ReportType")
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    ContentType = apps.get_model("contenttypes", "ContentType")

    Comment = get_apps_model(apps, "baseapp_comments", "Comment")
    Page = get_apps_model(apps, "baseapp_pages", "Page")
    Profile = get_apps_model(apps, "baseapp_profiles", "Profile")
    comment_content_type = ContentType.objects.get_for_model(Comment)
    page_content_type = ContentType.objects.get_for_model(Page)
    profile_content_type = ContentType.objects.get_for_model(Profile)

    base_report_types = [
        {"key": "spam", "label": "Spam", "content_types": [comment_content_type]},
        {
            "key": "inappropriate",
            "label": "Inappropriate",
            "content_types": [comment_content_type],
        },
        {"key": "fake", "label": "Fake", "content_types": [comment_content_type]},
        {
            "key": "other",
            "label": "Other",
            "content_types": [comment_content_type, page_content_type, profile_content_type],
        },
        {
            "key": "scam",
            "label": "Scam or fraud",
            "content_types": [page_content_type, profile_content_type],
        },
        {
            "key": "adult_content",
            "label": "Adult Content",
            "content_types": [page_content_type, profile_content_type],
        },
        {
            "key": "violence",
            "label": "Violence, hate or exploitation",
            "content_types": [page_content_type, profile_content_type],
        },
        {
            "key": "bulling",
            "label": "Bulling or unwanted contact",
            "content_types": [page_content_type, profile_content_type],
        },
    ]

    adult_content_type = ""
    for type in base_report_types:
        rt = ReportType(key=type["key"], label=type["label"])
        rt.save()
        rt.content_types.set(type["content_types"])
        if type["key"] == "adult_content":
            adult_content_type = rt

    adult_content_subtypes_types = [
        {
            "key": "pornography",
            "label": "Pornography",
            "content_types": [page_content_type, profile_content_type],
        },
        {
            "key": "childAbuse",
            "label": "Child abuse",
            "content_types": [page_content_type, profile_content_type],
        },
        {
            "key": "prostituition",
            "label": "Prostituition",
            "content_types": [page_content_type, profile_content_type],
        },
    ]

    for subtype in adult_content_subtypes_types:
        rt = ReportType(key=subtype["key"], label=subtype["label"], parent_type=adult_content_type)
        rt.save()
        rt.content_types.set(subtype["content_types"])

    for report in Report.objects.all():
        report_type = ReportType.objects.filter(key=report.report_type).first()
        report.report_type_fk = report_type
        report.save(update_fields=["report_type_fk"])


def reverse_create_default_report_types(apps, schema_editor):
    ReportType = get_apps_model(apps, "baseapp_reports", "ReportType")
    Report = get_apps_model(apps, "baseapp_reports", "Report")

    ReportType.objects.all().delete()

    for report in Report.objects.all():
        report.report_type_fk = None
        report.save(update_fields=["report_type_fk"])


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_reports", "0004_alter_report_report_type_reporttype"),
    ]

    operations = [
        migrations.RunPython(
            create_default_report_types_and_transfer_values, reverse_create_default_report_types
        ),
    ]
