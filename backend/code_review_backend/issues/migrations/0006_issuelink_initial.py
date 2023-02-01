# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Generated by Django 4.1.2 on 2022-12-07 16:59

import django.db.models.deletion
from django.db import migrations
from django.db import models


def clean_unlinked_issue(apps, schema_editor):
    """Delete issues that have no diff"""
    Issue = apps.get_model("issues", "Issue")
    deleted, _ = Issue.objects.filter(diff__isnull=True).delete()
    print(f"Deleted {deleted} issues that were missing a diff.")


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
        # Clean issues that are linked to no diff (such issues should not exist)
        migrations.RunPython(
            clean_unlinked_issue,
            # Make that step non reversible so we do not loose newly published annotations
            reverse_code=None,
            elidable=True,
        ),
    ]
