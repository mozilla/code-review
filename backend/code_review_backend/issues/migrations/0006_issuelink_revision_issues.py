# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Generated by Django 4.1.2 on 2022-12-07 16:59

from math import ceil

import django.db.models.deletion
from django.db import migrations
from django.db import models

ISSUES_INSERT_SIZE = 5000


def generate_issue_links(apps, schema_editor):
    """Generate the IssueLink M2M table from issues' FK to the diff of a revision"""
    Issue = apps.get_model("issues", "Issue")
    IssueLink = apps.get_model("issues", "IssueLink")
    qs = (
        Issue.objects.filter(old_diff__isnull=False)
        .order_by("created", "id")
        .values("id", "old_diff_id", "old_diff__revision_id")
    )

    issues_count = qs.count()
    slices = ceil(issues_count / ISSUES_INSERT_SIZE)

    for index in range(0, slices):
        print(
            f"[{index + 1}/{slices}] Initializing Issues references on the M2M table."
        )
        issues = qs[index * ISSUES_INSERT_SIZE : (index + 1) * ISSUES_INSERT_SIZE]
        IssueLink.objects.bulk_create(
            (
                IssueLink(
                    issue_id=issue["id"],
                    diff_id=issue["old_diff_id"],
                    revision_id=issue["old_diff__revision_id"],
                )
                for issue in issues
            )
        )


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0005_rename_check_issue_analyzer_check"),
    ]

    operations = [
        # Create the M2M table
        migrations.CreateModel(
            name="IssueLink",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "diff",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issue_links",
                        to="issues.diff",
                    ),
                ),
                (
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issue_links",
                        to="issues.issue",
                    ),
                ),
                (
                    "revision",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issue_links",
                        to="issues.revision",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="issuelink",
            constraint=models.UniqueConstraint(
                condition=models.Q(("diff__isnull", True)),
                fields=("issue", "revision"),
                name="issue_link_unique_revision",
            ),
        ),
        migrations.AddConstraint(
            model_name="issuelink",
            constraint=models.UniqueConstraint(
                condition=models.Q(("diff__isnull", False)),
                fields=("issue", "revision", "diff"),
                name="issue_link_unique_diff",
            ),
        ),
        # Update Issue model to support both relations
        migrations.AlterField(
            model_name="issue",
            name="diff",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="old_issues",
                to="issues.diff",
            ),
        ),
        migrations.RenameField(
            model_name="issue",
            old_name="diff",
            new_name="old_diff",
        ),
        migrations.AlterModelOptions(
            name="issue",
            options={"ordering": ("created",)},
        ),
        # Add relational fields
        migrations.AddField(
            model_name="issue",
            name="revisions",
            field=models.ManyToManyField(
                related_name="issues", through="issues.IssueLink", to="issues.revision"
            ),
        ),
        migrations.AddField(
            model_name="issue",
            name="diffs",
            field=models.ManyToManyField(
                related_name="issues", through="issues.IssueLink", to="issues.diff"
            ),
        ),
        # Fill the M2M table
        migrations.RunPython(
            generate_issue_links,
            reverse_code=migrations.RunPython.noop,
            elidable=True,
        ),
        # Drop old FK
        migrations.RemoveField(
            model_name="issue",
            name="old_diff",
        ),
    ]
