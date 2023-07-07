# Generated by Django 3.2.12 on 2022-04-25 16:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("baseapp_auth", "0004_auto_20160811_1614"),
    ]

    operations = [
        migrations.CreateModel(
            name="PasswordValidation",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        choices=[
                            (
                                "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
                                "User Attribute Similarity",
                            ),
                            (
                                "django.contrib.auth.password_validation.MinimumLengthValidator",
                                "Minimum Length",
                            ),
                            (
                                "django.contrib.auth.password_validation.CommonPasswordValidator",
                                "Common Password",
                            ),
                            (
                                "django.contrib.auth.password_validation.NumericPasswordValidator",
                                "Numeric Password",
                            ),
                            (
                                "baseapp_auth.password_validators.MustContainCapitalLetterValidator",
                                "Must Contain Capital Letter",
                            ),
                            (
                                "baseapp_auth.password_validators.MustContainSpecialCharacterValidator",
                                "Must Contain Special Character",
                            ),
                        ],
                        max_length=255,
                    ),
                ),
                ("options", models.JSONField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
        ),
    ]
