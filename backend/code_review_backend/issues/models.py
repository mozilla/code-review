# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib
import os
import urllib.parse
import uuid

import requests
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


class Repository(PhabricatorModel):

    url = models.URLField(unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name_plural = "repositories"

    def __str__(self):
        return self.slug


class Revision(PhabricatorModel):
    repository = models.ForeignKey(
        Repository, related_name="revisions", on_delete=models.CASCADE
    )

    title = models.CharField(max_length=250)
    bugzilla_id = models.PositiveIntegerField(null=True)

    def __str__(self):
        return f"D{self.id} - {self.title}"


class Diff(PhabricatorModel):
    revision = models.ForeignKey(
        Revision, related_name="diffs", on_delete=models.CASCADE
    )

    review_task_id = models.CharField(max_length=30, unique=True)
    mercurial = models.CharField(max_length=40)

    def __str__(self):
        return f"Diff {self.id}"

    def load_file(self, path):
        """
        Load a file content at patch's revision
        Using remote HGMO
        """
        # Check in hgmo cache first
        local_path = os.path.join(
            settings.HGMO_CACHE, self.revision.repository.slug, path, self.mercurial
        )
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        if os.path.exists(local_path):
            return open(local_path).read()

        # Retrieve remote file
        url = urllib.parse.urljoin(
            self.revision.repository.url, f"raw-file/{self.mercurial}/{path}"
        )
        print("Downloading", url)
        response = requests.get(url)
        response.raise_for_status()

        # Store in cache
        content = response.content.decode("utf-8")
        with open(local_path, "w") as f:
            f.write(content)

        return content


class Issue(models.Model):
    """An issue detected on a Phabricator patch"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    diff = models.ForeignKey(Diff, related_name="issues", on_delete=models.CASCADE)

    # Raw issue data
    path = models.CharField(max_length=250)
    line = models.PositiveIntegerField()
    nb_lines = models.PositiveIntegerField()
    char = models.PositiveIntegerField(null=True)
    level = models.CharField(max_length=20, choices=ISSUE_LEVELS)
    check = models.CharField(max_length=250, null=True)
    message = models.TextField(null=True)
    analyzer = models.CharField(max_length=50)

    # Calculated hash identifying issue
    hash = models.CharField(max_length=32, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def get_lines(self):
        """Load all the lines affected by the issue"""
        file_content = self.diff.load_file(self.path)
        file_lines = file_content.splitlines()
        start = self.line - 1  # file_lines start at 0, not 1
        return file_lines[start : start + self.nb_lines]  # noqa E203

    def build_hash(self):

        # Build raw content:
        # 1. lines affected by patch
        # 2. without any spaces around each line
        try:
            raw_content = "".join([line.strip() for line in self.get_lines()])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return
            raise

        # Build hash payload using issue data
        # excluding file position information (lines & char)
        payload = ":".join(
            [self.path, self.analyzer, self.check or "", raw_content]
        ).encode("utf-8")

        # Finally build the MD5 hash
        return hashlib.md5(payload).hexdigest()
