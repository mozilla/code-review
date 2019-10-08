# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import uuid

from django.db import models


class PhabricatorModel(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    phid = models.CharField(max_length=40, unique=True)

    class Meta:
        abstract = True


class Repository(PhabricatorModel):

    url = models.URLField(unique=True)
    slug = models.SlugField(unique=True)


class Revision(PhabricatorModel):
    repository = models.ForeignKey(
        Repository, related_name="revisions", on_delete=models.CASCADE
    )

    title = models.CharField(max_length=250)


class Diff(PhabricatorModel):
    revision = models.ForeignKey(
        Revision, related_name="diffs", on_delete=models.CASCADE
    )


class Issue(models.Model):
    """An issue detected on a Phabricator patch"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    diff = models.ForeignKey(Diff, related_name="issues", on_delete=models.CASCADE)
