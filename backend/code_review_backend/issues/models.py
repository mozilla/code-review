# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import urllib.parse
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

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


class Revision(models.Model):
    id = models.BigAutoField(primary_key=True)
    # Phabricator references will be left empty when ingesting a decision task (e.g. from MC or autoland)
    phabricator_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    phabricator_phid = models.CharField(
        max_length=40, unique=True, null=True, blank=True
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    base_repository = models.ForeignKey(
        Repository,
        related_name="base_revisions",
        on_delete=models.CASCADE,
        help_text="Target repository where the revision has been produced and will land in the end",
    )
    head_repository = models.ForeignKey(
        Repository,
        related_name="head_revisions",
        on_delete=models.CASCADE,
        help_text="Repository where the revision is actually analyzed (e.g. Try for patches analysis)",
    )

    base_changeset = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        help_text="Mercurial hash identifier on the base repository",
    )
    head_changeset = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        help_text="Mercurial hash identifier on the analyze repository (only set for try pushes)",
    )

    title = models.CharField(max_length=250)
    bugzilla_id = models.PositiveIntegerField(null=True)

    class Meta:
        ordering = ("phabricator_id", "id")

        indexes = (models.Index(fields=["head_repository", "head_changeset"]),)
        constraints = [
            models.UniqueConstraint(
                fields=["phabricator_id"],
                name="revision_unique_phab_id",
                condition=Q(phabricator_id__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["phabricator_phid"],
                name="revision_unique_phab_phabid",
                condition=Q(phabricator_phid__isnull=False),
            ),
        ]

    def __str__(self):
        if self.phabricator_id is not None:
            return f"D{self.phabricator_id} - {self.title}"
        return f"#{self.id} - {self.title}"

    @property
    def phabricator_url(self):
        if self.phabricator_id is None:
            return
        parser = urllib.parse.urlparse(settings.PHABRICATOR_HOST)
        return f"{parser.scheme}://{parser.netloc}/D{self.phabricator_id}"


class Diff(PhabricatorModel):
    """Reference of a specific code patch (diff) in Phabricator.
    A revision can be linked to multiple successive diffs, or none in case of a repository push.
    """

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


class IssueLink(models.Model):
    """Many-to-many relationship between an Issue and a Revision.
    A Diff can be set to track issues evolution on a revision with multiple diffs.
    """

    id = models.BigAutoField(primary_key=True)
    revision = models.ForeignKey(
        "issues.Revision",
        on_delete=models.CASCADE,
        related_name="issue_links",
    )
    issue = models.ForeignKey(
        "issues.Issue",
        on_delete=models.CASCADE,
        related_name="issue_links",
    )
    diff = models.ForeignKey(
        "issues.Diff",
        on_delete=models.CASCADE,
        related_name="issue_links",
        null=True,
        blank=True,
    )

    # Is this issue new for this revision ?
    # Can be null (not set by API) when a revision is not linked to a diff
    new_for_revision = models.BooleanField(null=True)

    # Is this issue present in the patch ?
    # Can be null (not set by API) when a revision is not linked to a diff
    in_patch = models.BooleanField(null=True)

    # Issue position on the file
    line = models.PositiveIntegerField(null=True)
    nb_lines = models.PositiveIntegerField(null=True)
    char = models.PositiveIntegerField(null=True)

    class Meta:
        constraints = [
            # Two constraints are required as Null values are not compared for unicity
            models.UniqueConstraint(
                fields=["issue", "revision", "line", "nb_lines", "char"],
                name="issue_link_unique_revision",
                condition=Q(diff__isnull=True),
            ),
            models.UniqueConstraint(
                fields=["issue", "revision", "diff", "line", "nb_lines", "char"],
                name="issue_link_unique_diff",
                condition=Q(diff__isnull=False),
            ),
        ]

    @property
    def publishable(self):
        """Is that issue publishable on Phabricator to developers"""
        return self.in_patch is True or self.issue.level == LEVEL_ERROR


class Issue(models.Model):
    """An issue detected on a Phabricator patch"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    revisions = models.ManyToManyField(
        "issues.Revision",
        through="issues.IssueLink",
        related_name="issues",
    )
    diffs = models.ManyToManyField(
        "issues.Diff",
        through="issues.IssueLink",
        related_name="issues",
    )

    # Raw issue data
    path = models.CharField(max_length=250)
    level = models.CharField(max_length=20, choices=ISSUE_LEVELS)
    analyzer_check = models.CharField(max_length=250, null=True)
    message = models.TextField(null=True)
    analyzer = models.CharField(max_length=50)

    # Calculated hash identifying issue
    hash = models.CharField(max_length=32, unique=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created",)
        indexes = (
            models.Index(fields=["hash"], name="issue_hash_idx"),
            models.Index(fields=["path"]),
        )
