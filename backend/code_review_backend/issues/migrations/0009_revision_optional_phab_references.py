# -*- coding: utf-8 -*-
# Generated by Django 4.0.5 on 2023-04-14 15:37

from django.db import migrations, models
from django.db.models import F


def populate_phabricator_id(apps, schema_editor):
    """
    Before that migration, revisions used the Phabricator
    numerical ID as their primary key.
    """
    Revision = apps.get_model("issues", "Revision")
    Revision.objects.all().update(phabricator_id=F("id"))


class Migration(migrations.Migration):
    dependencies = [
        ("issues", "0008_revision_base_head_references"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="revision",
            options={"ordering": ("phabricator_id", "id")},
        ),
        migrations.AddField(
            model_name="revision",
            name="phabricator_id",
            field=models.PositiveIntegerField(blank=True, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name="revision",
            name="phid",
            field=models.CharField(blank=True, max_length=40, null=True, unique=True),
        ),
        migrations.RenameField(
            model_name="revision",
            old_name="phid",
            new_name="phabricator_phid",
        ),
        migrations.RunPython(
            populate_phabricator_id,
            reverse_code=migrations.RunPython.noop,
            elidable=True,
        ),
        migrations.AlterField(
            model_name="revision",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.AddConstraint(
            model_name="revision",
            constraint=models.UniqueConstraint(
                condition=models.Q(("phabricator_id__isnull", False)),
                fields=("phabricator_id",),
                name="revision_unique_phab_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="revision",
            constraint=models.UniqueConstraint(
                condition=models.Q(("phabricator_phid__isnull", False)),
                fields=("phabricator_phid",),
                name="revision_unique_phab_phabid",
            ),
        ),
    ]