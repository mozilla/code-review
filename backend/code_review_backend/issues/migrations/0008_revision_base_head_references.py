# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Count, F, OuterRef, Q, Subquery


def update_revisions(apps, schema_editor):
    """
    Detect the head repository depending on the current data:
     - all revisions without any diff use their current head repo
     - all revisions with a only diffs on autoland use it as their head repo
    """
    Repository = apps.get_model("issues", "Repository")
    Revision = apps.get_model("issues", "Revision")
    Diff = apps.get_model("issues", "Diff")

    # No need to run the following lines if the db is empty (e.g. during tests)
    if not Revision.objects.exists():
        return

    # all revisions without any diff get their head repo as revision.repository_id
    Revision.objects.filter(diffs__isnull=True).update(
        head_repository_id=F("base_repository_id")
    )

    # all revisions with only diff on autoland use it as their head repo
    autoland = Repository.objects.get(slug="autoland")
    others = Repository.objects.exclude(id=autoland.id)
    Revision.objects.annotate(
        other_diffs=Count("diffs", filter=Q(diffs__repository__in=others))
    ).filter(other_diffs=0, diffs__repository_id=autoland.id).update(
        head_repository_id=autoland.id
    )

    # all revisions without any diff excluding diffs with autoland repo
    # get their head repo as diff.repository_id
    rev_repos = (
        Diff.objects.filter(revision_id=OuterRef("id"))
        .exclude(repository_id=autoland.id)
        .values("repository_id")[:1]
    )
    Revision.objects.filter(head_repository_id__isnull=True).update(
        head_repository_id=Subquery(rev_repos)
    )

    # Check no revisions miss their head repos
    assert not Revision.objects.filter(
        head_repository__isnull=True
    ).exists(), "Some revisions miss their head repos"


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
        # Revision mercurial changeset reference is set to null on existing revisions
        migrations.AddField(
            model_name="revision",
            name="base_changeset",
            field=models.CharField(
                max_length=40,
                help_text="Mercurial hash identifier on the base repository",
                null=True,
                blank=True,
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
                null=False,
            ),
        ),
    ]
