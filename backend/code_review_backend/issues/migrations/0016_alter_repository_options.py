# Generated by Django 5.1.2 on 2024-11-18 15:55

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("issues", "0015_remove_repository_phid_alter_repository_id"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="repository",
            options={"ordering": ("id",), "verbose_name_plural": "repositories"},
        ),
    ]
