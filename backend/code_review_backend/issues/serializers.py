# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from rest_framework import serializers

from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Repository
from code_review_backend.issues.models import Revision


class RepositorySerializer(serializers.ModelSerializer):
    """
    Serialize a Repository
    """

    class Meta:
        model = Repository
        fields = ("id", "phid", "slug", "url")


class RevisionSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize a Revision in a Repository
    """

    repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="slug"
    )

    class Meta:
        model = Revision
        fields = ("id", "repository", "phid", "title", "bugzilla_id")


class DiffSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize a Diff in a Revision
    """

    revision = serializers.PrimaryKeyRelatedField(queryset=Revision.objects.all())
    issues_url = serializers.HyperlinkedIdentityField(
        view_name="issues-list", lookup_url_kwarg="diff_id"
    )

    class Meta:
        model = Diff
        fields = (
            "id",
            "revision",
            "phid",
            "review_task_id",
            "mercurial_hash",
            "issues_url",
        )


class IssueSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize an Issue in a Diff
    """

    class Meta:
        model = Issue
        fields = (
            "id",
            "hash",
            "analyzer",
            "path",
            "line",
            "nb_lines",
            "char",
            "level",
            "check",
            "message",
        )


class IssueCheckSerializer(serializers.Serializer):
    """
    Serialize the usage statistics for each check encountered
    """

    repository = serializers.CharField(source="diff__revision__repository__slug")
    analyzer = serializers.CharField()
    check = serializers.CharField()
    total = serializers.IntegerField()

    # TODO: support publishable stats number once we have hash comparison stored
    publishable = serializers.IntegerField(default=0)
