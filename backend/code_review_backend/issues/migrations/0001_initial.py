# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Generated by Django 2.2.6 on 2019-10-17 15:23

import uuid

import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Diff",
            fields=[
                ("id", models.PositiveIntegerField(primary_key=True, serialize=False)),
                ("phid", models.CharField(max_length=40, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("review_task_id", models.CharField(max_length=30, unique=True)),
                ("mercurial_hash", models.CharField(max_length=40)),
            ],
            options={"ordering": ("id",), "abstract": False},
        ),
        migrations.CreateModel(
            name="Repository",
            fields=[
                ("id", models.PositiveIntegerField(primary_key=True, serialize=False)),
                ("phid", models.CharField(max_length=40, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("slug", models.SlugField(unique=True)),
                ("url", models.URLField(unique=True)),
                ("try_url", models.URLField(blank=True, null=True)),
            ],
            options={"verbose_name_plural": "repositories"},
        ),
        migrations.CreateModel(
            name="Revision",
            fields=[
                ("id", models.PositiveIntegerField(primary_key=True, serialize=False)),
                ("phid", models.CharField(max_length=40, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=250)),
                ("bugzilla_id", models.PositiveIntegerField(null=True)),
                (
                    "repository",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revisions",
                        to="issues.Repository",
                    ),
                ),
            ],
            options={"ordering": ("id",), "abstract": False},
        ),
        migrations.CreateModel(
            name="Issue",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, primary_key=True, serialize=False
                    ),
                ),
                ("path", models.CharField(max_length=250)),
                ("line", models.PositiveIntegerField(null=True)),
                ("nb_lines", models.PositiveIntegerField(null=True)),
                ("char", models.PositiveIntegerField(null=True)),
                (
                    "level",
                    models.CharField(
                        choices=[("warning", "Warning"), ("error", "Error")],
                        max_length=20,
                    ),
                ),
                ("check", models.CharField(max_length=250, null=True)),
                ("message", models.TextField(null=True)),
                ("analyzer", models.CharField(max_length=50)),
                ("hash", models.CharField(max_length=32)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "diff",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issues",
                        to="issues.Diff",
                    ),
                ),
            ],
            options={"ordering": ("diff", "path", "line", "analyzer")},
        ),
        migrations.AddField(
            model_name="diff",
            name="revision",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="diffs",
                to="issues.Revision",
            ),
        ),
    ]
