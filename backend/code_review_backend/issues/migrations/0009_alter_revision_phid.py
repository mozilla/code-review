# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import uuid

from django.db import migrations
from django.db import models


def populate_uuids(apps, schema_editor):
    """
    Populate UUIDs on Revision rows, that will be used as the new PK.
    Postgres support generating UUIDs from the backend directly.
    """
    if "postgresql" in schema_editor.connection.vendor:
        schema_editor.execute("INSERT INTO issues_revision id SELECT gen_random_uuid()")
    else:
        # Default to updating new PKs in bulk for developers
        Revision = apps.get_model("issues", "Revision")
        revs = Revision.objects.only("phabricator_id")
        for rev in revs:
            rev.id = uuid.uuid4()
        Revision.objects.bulk_update(revs, ["id"])


class Migration(migrations.Migration):
    dependencies = [
        ("issues", "0008_revision_base_head_references"),
    ]
    operations = [
        migrations.AlterModelOptions(
            name="revision",
            options={"ordering": ("phabricator_id", "id")},
        ),
        # Rename the original Revision Phabricator PK
        migrations.RenameField(
            model_name="revision",
            old_name="id",
            new_name="phabricator_id",
        ),
        # Populate the field that will contain the future Revision UUID PK
        migrations.AddField(
            model_name="revision",
            name="id",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(
            populate_uuids,
            reverse_code=migrations.RunPython.noop,
            elidable=True,
        ),
        # Add a field on IssueLink and Diff models that references the new UUID field
        migrations.AddField(
            model_name="issuelink",
            name="revision_new_fk",
            field=models.UUIDField(null=True),
        ),
        migrations.RunSQL(
            """
            UPDATE issues_issuelink SET revision_new_fk = (
                SELECT issues_revision.id
                FROM issues_revision
                WHERE issues_revision.phabricator_id = issues_issuelink.revision_id
            )
            """
        ),
        migrations.AddField(
            model_name="diff",
            name="revision_new_fk",
            field=models.UUIDField(null=True),
        ),
        migrations.RunSQL(
            """
            UPDATE issues_diff SET revision_new_fk = (
                SELECT issues_revision.id
                FROM issues_revision
                WHERE issues_revision.phabricator_id = issues_diff.revision_id
            )
            """
        ),
        # Update the PK on the Revision model
        migrations.AlterField(
            model_name="revision",
            name="id",
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, primary_key=True, serialize=False
            ),
        ),
        migrations.AlterField(
            model_name="revision",
            name="phabricator_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="revision",
            name="phid",
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        # Update the Foreign key on IssueLink and Diff models
        migrations.AlterField(
            model_name="issuelink",
            name="revision_new_fk",
            field=models.ForeignKey(
                "issues.Revision",
                on_delete=models.CASCADE,
                related_name="issue_links",
            ),
        ),
        migrations.AlterField(
            model_name="issuelink",
            name="revision",
            field=models.PositiveIntegerField(),
        ),
        migrations.RemoveField(
            model_name="issuelink",
            name="revision",
        ),
        migrations.AlterField(
            model_name="diff",
            name="revision_new_fk",
            field=models.ForeignKey(
                "issues.Revision",
                on_delete=models.CASCADE,
                related_name="diffs",
            ),
        ),
        migrations.AlterField(
            model_name="diff",
            name="revision",
            field=models.PositiveIntegerField(),
        ),
        migrations.RemoveField(
            model_name="diff",
            name="revision",
        ),
        # Rename fields
        migrations.RenameField(
            model_name="issuelink",
            old_name="revision_new_fk",
            new_name="revision",
        ),
        migrations.RenameField(
            model_name="diff",
            old_name="revision_new_fk",
            new_name="revision",
        ),
        migrations.RenameField(
            model_name="revision",
            old_name="phid",
            new_name="phabricator_phid",
        ),
        # Add constraints
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
