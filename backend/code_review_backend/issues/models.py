# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import urllib.parse
import uuid

from django.conf import settings
from django.db import models

LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"
ISSUE_LEVELS = ((LEVEL_WARNING, "Warning"), (LEVEL_ERROR, "Error"))


class PhabricatorModel(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    phid = models.CharField(max_length=40, unique=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("id",)


class Repository(PhabricatorModel):
    # Not all repositories are available on Phabricator (Try ones)
    phid = models.CharField(max_length=40, unique=False, null=True, blank=True)

    slug = models.SlugField(unique=True)
    url = models.URLField(unique=True)

    class Meta:
        verbose_name_plural = "repositories"

    def __str__(self):
        return self.slug


class Revision(PhabricatorModel):
    # The target repository where the revision will land in the end
    repository = models.ForeignKey(
        Repository, related_name="revisions", on_delete=models.CASCADE
    )

    title = models.CharField(max_length=250)
    bugzilla_id = models.PositiveIntegerField(null=True)

    def __str__(self):
        return f"D{self.id} - {self.title}"

    @property
    def phabricator_url(self):
        parser = urllib.parse.urlparse(settings.PHABRICATOR_HOST)
        return f"{parser.scheme}://{parser.netloc}/D{self.id}"


class Diff(PhabricatorModel):
    revision = models.ForeignKey(
        Revision, related_name="diffs", on_delete=models.CASCADE
    )

    review_task_id = models.CharField(max_length=30, unique=True)

    mercurial_hash = models.CharField(max_length=40)

    # The repository hosting this specific mercurial revision (try, autoland, ...)
    repository = models.ForeignKey(
        Repository, related_name="diffs", on_delete=models.CASCADE
    )

    def __str__(self):
        return f"Diff {self.id}"


class Issue(models.Model):
    """An issue detected on a Phabricator patch"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    # Diff can be null to support issues without any link to Phabricator
    # like the issues used to initialize the database on a full tree analyzer run
    diff = models.ForeignKey(
        Diff, related_name="issues", on_delete=models.CASCADE, null=True, blank=True
    )

    # Raw issue data
    path = models.CharField(max_length=250)
    line = models.PositiveIntegerField(null=True)
    nb_lines = models.PositiveIntegerField(null=True)
    char = models.PositiveIntegerField(null=True)
    level = models.CharField(max_length=20, choices=ISSUE_LEVELS)
    check = models.CharField(max_length=250, null=True)
    message = models.TextField(null=True)
    analyzer = models.CharField(max_length=50)

    # Calculated hash identifying issue
    hash = models.CharField(max_length=32)

    # Is this issue new for this revision ?
    # Can be null (not set by API) when a revision is not linked to a diff
    new_for_revision = models.BooleanField(null=True)

    # Is this issue present in the patch ?
    # Can be null (not set by API) when a revision is not linked to a diff
    in_patch = models.BooleanField(null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("diff", "path", "line", "analyzer")

    @property
    def publishable(self):
        """Is that issue publishable on Phabricator to developers"""
        return self.in_patch is True or self.level == LEVEL_ERROR
