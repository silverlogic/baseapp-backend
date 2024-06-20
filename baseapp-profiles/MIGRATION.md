If you have a project that have profiles before using "baseapp-profiles" this is what you need to do to migrate:

Extend the models from "baseapp_profiles.models.ProfilableModel" and make sure to override the "profile" field to make it nullable:

```python
from baseapp_profiles.models import ProfilableModel


class User(ProfilableModel):
    pass
```

Then create migrations and apply them

Then create an data migration to populate profiles from the old model to the new one:

```
./manage.py makemigrations --empty -n migrate_users users
```

Then edit the migration file with the correct code based on your profile model, for example:

```python
from django.db import migrations

class Migration(migrations.Migration):
    def forwards_func(apps, _):
        ContentType = apps.get_model("contenttypes", "ContentType")
        BandProfile = apps.get_model("bands", "BandProfile")
        Profile = apps.get_model("profiles", "Profile")

        for band in BandProfile.objects.all():
            if not band.profile_id:
                target_content_type = ContentType.objects.get_for_model(band)

                profile = Profile.objects.create(
                    name=band.name,
                    avatar=band.profile_image,
                    target_content_type=target_content_type,
                    target_object_id=band.pk
                )

                band.profile = profile
                band.save(update_fields=["profile"])

    def reverse_func(apps, _):
        pass

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("profiles", "0001_initial"),
        ("bands", "0033_remove_bandprofile_snapshot_insert_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
```

- Apply the migration

- Add signals to update profile when the target model changes, can be pgtriggers
