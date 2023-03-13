# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import secrets

import django.db.models.deletion
from django.db import migrations
from django.db import models
from django.db.models import F

# A django command can help restauring real hashes later on.


def update_revisions(apps, schema_editor):
    """
    Detect the head repository depending on the current data:
    * All revisions on MC or autoland or unified with some Diff are from try.
    * All revisions on MC without any Diff are recent mozilla-central ingestions.
    * All revisions on NSS are coming from NSS-try.
    """
    Repository = apps.get_model("issues", "Repository")
    Revision = apps.get_model("issues", "Revision")

    try_repository = Repository.objects.get(slug="try")
    Revision.objects.filter(diffs__isnull=False).update(
        head_repository_id=try_repository.id
    )
    Revision.objects.filter(diffs__isnull=True).update(
        head_repository_id=F("base_repository_id")
    )


class Migration(migrations.Migration):
    dependencies = [
        ("issues", "0007_issuelink_swap"),
    ]

    operations = [
        migrations.RenameField(
            model_name="revision",
            old_name="repository",
            new_name="base_repository",
        ),
        migrations.AlterField(
            model_name="revision",
            name="base_repository",
            field=models.ForeignKey(
                help_text="Target repository where the revision has been produced and will land in the end",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="base_revisions",
                to="issues.repository",
            ),
        ),
        migrations.AddField(
            model_name="revision",
            name="head_repository",
            # Make the field temporarily nullable so it can be set on existing revisions
            field=models.ForeignKey(
                to="issues.repository",
                on_delete=django.db.models.deletion.CASCADE,
                null=True,
            ),
        ),
        # Revision mercurial changeset reference is set to a random value on existing revisions
        migrations.AddField(
            model_name="revision",
            name="base_changeset",
            field=models.CharField(
                max_length=40,
                help_text="Mercurial hash identifier on the base repository",
                default=lambda: secrets.token_hex(40),
            ),
            preserve_default=False,
        ),
        # Head revision is set to null on existing revisions
        migrations.AddField(
            model_name="revision",
            name="head_changeset",
            field=models.CharField(
                help_text="Mercurial hash identifier on the analyze repository (only set for try pushes)",
                max_length=40,
                null=True,
                blank=True,
            ),
        ),
        migrations.RunPython(
            update_revisions,
            reverse_code=migrations.RunPython.noop,
            elidable=True,
        ),
        # Make head_repository a required field
        migrations.AlterField(
            model_name="revision",
            name="head_repository",
            field=models.ForeignKey(
                help_text="Repository where the revision is actually analyzed (e.g. Try for patches analysis)",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="head_revisions",
                to="issues.repository",
            ),
        ),
    ]
