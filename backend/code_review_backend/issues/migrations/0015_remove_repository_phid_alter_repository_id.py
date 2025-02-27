# Generated by Django 5.1.2 on 2024-11-18 15:53

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("issues", "0014_unique_hash"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="repository",
            name="phid",
        ),
        migrations.AlterField(
            model_name="repository",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterModelOptions(
            name="repository",
            options={"ordering": ("id",), "verbose_name_plural": "repositories"},
        ),
    ]
    if "postgresql" in settings.DATABASES["default"]["ENGINE"]:
        print(
            "Adding sequence initialization for Repository PK to issues.0015 with PostgreSQL backend"
        )
        operations.append(
            migrations.RunSQL(
                """
                SELECT setval(
                    pg_get_serial_sequence('issues_repository', 'id'),
                    coalesce(max(id)+1, 1),
                    false
                ) FROM issues_repository;
                """,
                reverse_sql=migrations.RunSQL.noop,
            )
        )
