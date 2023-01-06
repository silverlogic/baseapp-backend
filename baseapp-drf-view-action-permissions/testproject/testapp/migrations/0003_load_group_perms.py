from django.db import migrations

from permissions.utils import get_permission_loader, get_permission_remover

permissions = [
    {"name": "Test Group", "permissions": ['list_tests', 'test_disable', 'custom_action_testmodel'],},
]


class Migration(migrations.Migration):

    dependencies = [
        ("testapp", "0002_alter_testmodel_options"),
    ]

    operations = [
        migrations.RunPython(get_permission_loader(permissions=permissions), get_permission_remover(permissions=permissions, remove_group=True)),
    ]
