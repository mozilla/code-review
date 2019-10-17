# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from rest_framework import serializers

from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Repository
from code_review_backend.issues.models import Revision


class RevisionSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize a Revision in a repository
    """

    repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="slug"
    )

    class Meta:
        model = Revision
        fields = ("id", "repository", "phid", "title", "bugzilla_id")


class DiffSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize a Diff in a revision
    """

    revision = serializers.PrimaryKeyRelatedField(queryset=Revision.objects.all())

    class Meta:
        model = Diff
        fields = ("id", "revision", "phid", "review_task_id", "mercurial")
