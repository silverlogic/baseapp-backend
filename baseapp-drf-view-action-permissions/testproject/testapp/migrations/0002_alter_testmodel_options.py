# Generated by Django 3.2.16 on 2023-01-06 17:13

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('testapp', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='testmodel',
            options={'permissions': [('view_testmodel_list', 'Can List all testmodel'), ('test_disable', 'Can disable test'), ('list_tests', 'Can list tests'), ('custom_action_testmodel', 'Can custom action testmodel'), ('custom_detail_action_testmodel', 'Can custom detail action testmodel')]},
        ),
    ]
