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


class RevisionSerializer(serializers.ModelSerializer):
    """
    Serialize a Revision in a Repository
    """

    repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="url"
    )
    diffs_url = serializers.HyperlinkedIdentityField(
        view_name="revision-diffs-list", lookup_url_kwarg="revision_id"
    )
    phabricator_url = serializers.URLField(read_only=True)

    class Meta:
        model = Revision
        fields = (
            "id",
            "repository",
            "phid",
            "title",
            "bugzilla_id",
            "diffs_url",
            "phabricator_url",
        )


class DiffSerializer(serializers.ModelSerializer):
    """
    Serialize a Diff in a Revision
    Used for full management
    """

    repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="url"
    )
    issues_url = serializers.HyperlinkedIdentityField(
        view_name="issues-list", lookup_url_kwarg="diff_id"
    )

    class Meta:
        model = Diff
        fields = (
            "id",
            "phid",
            "review_task_id",
            "repository",
            "mercurial_hash",
            "issues_url",
        )


class DiffFullSerializer(serializers.ModelSerializer):
    """
    Serialize a Diff with revision details
    This is used in a read only context
    """

    revision = RevisionSerializer(read_only=True)
    repository = RepositorySerializer(read_only=True)
    issues_url = serializers.HyperlinkedIdentityField(
        view_name="issues-list", lookup_url_kwarg="diff_id"
    )
    nb_issues = serializers.IntegerField(read_only=True)
    nb_issues_new_for_revision = serializers.IntegerField(read_only=True)

    class Meta:
        model = Diff
        fields = (
            "id",
            "revision",
            "phid",
            "review_task_id",
            "repository",
            "mercurial_hash",
            "issues_url",
            "nb_issues",
            "nb_issues_new_for_revision",
            "created",
        )


class IssueSerializer(serializers.ModelSerializer):
    """
    Serialize an Issue in a Diff
    """

    publishable = serializers.BooleanField(read_only=True)

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
            "new_for_revision",
            "in_patch",
            "publishable",
        )
        read_only_fields = ("new_for_revision",)


class IssueCheckSerializer(serializers.Serializer):
    """
    Serialize the usage statistics for each check encountered
    """

    repository = serializers.CharField(source="diff__revision__repository__slug")
    analyzer = serializers.CharField()
    check = serializers.CharField()
    total = serializers.IntegerField()
    publishable = serializers.IntegerField(default=0)


class HistoryPointSerializer(serializers.Serializer):
    """
    Serialize a data point for issue checks history graphs
    """

    date = serializers.DateField()
    total = serializers.IntegerField()
