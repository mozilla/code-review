# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.db import transaction
from rest_framework import serializers

from code_review_backend.issues.models import (
    Diff,
    Issue,
    IssueLink,
    Repository,
    Revision,
)


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

    base_repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="url"
    )
    head_repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="url"
    )
    diffs_url = serializers.HyperlinkedIdentityField(
        view_name="revision-diffs-list", lookup_url_kwarg="revision_id"
    )
    issues_bulk_url = serializers.HyperlinkedIdentityField(
        view_name="revision-issues-bulk", lookup_url_kwarg="revision_id"
    )
    phabricator_url = serializers.URLField(read_only=True)
    phabricator_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=2147483647,
    )

    class Meta:
        model = Revision
        fields = (
            "id",
            "base_repository",
            "head_repository",
            "base_changeset",
            "head_changeset",
            "phabricator_id",
            "phabricator_phid",
            "title",
            "bugzilla_id",
            "diffs_url",
            "issues_bulk_url",
            "phabricator_url",
        )


class RevisionLightSerializer(serializers.ModelSerializer):
    """
    Serialize a Revision in a Diff light serializer
    """

    base_repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="url"
    )
    head_repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="url"
    )
    phabricator_url = serializers.URLField(read_only=True)

    class Meta:
        model = Revision
        fields = (
            "id",
            "phabricator_id",
            "base_repository",
            "head_repository",
            "base_changeset",
            "head_changeset",
            "phabricator_id",
            "title",
            "bugzilla_id",
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


class DiffLightSerializer(serializers.ModelSerializer):
    """
    Serialize a Diff from an Issue in a check
    """

    repository = serializers.SlugRelatedField(
        queryset=Repository.objects.all(), slug_field="url"
    )

    revision = RevisionLightSerializer()

    class Meta:
        model = Diff
        fields = ("id", "repository", "revision")


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
    nb_issues_publishable = serializers.IntegerField(read_only=True)
    nb_warnings = serializers.IntegerField(read_only=True)
    nb_errors = serializers.IntegerField(read_only=True)

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
            "nb_issues_publishable",
            "nb_warnings",
            "nb_errors",
            "created",
        )


class IssueSerializer(serializers.ModelSerializer):
    """
    Serialize an Issue in a Diff
    """

    publishable = serializers.BooleanField(read_only=True)
    check = serializers.CharField(source="analyzer_check", required=False)
    publishable = serializers.BooleanField(read_only=True)
    in_patch = serializers.BooleanField(source="issue__links__in_patch", read_only=True)
    new_for_revision = serializers.BooleanField(
        source="issue__links__new_for_revision",
        read_only=True,
    )

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
            # Attrs coming from IssueLink
            "publishable",
            "in_patch",
            "new_for_revision",
        )
        read_only_fields = ("new_for_revision",)


class IssueHashSerializer(serializers.ModelSerializer):
    """
    Serialize an Issue hash
    """

    class Meta:
        model = Issue
        fields = (
            "id",
            "hash",
        )
        read_only_fields = ("id", "hash")


class IssueBulkSerializer(serializers.Serializer):
    diff_id = serializers.PrimaryKeyRelatedField(
        # Initialized depending on the revision used for the creation
        queryset=Diff.objects.none(),
        style={"base_template": "input.html"},
        required=False,
        allow_null=True,
    )
    issues = IssueSerializer(many=True)
    issues.child.fields.update(
        {
            # Property set on the IssueLink M2M during creation
            "new_for_revision": serializers.BooleanField(default=None, write_only=True),
            "in_patch": serializers.BooleanField(default=None, write_only=True),
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context.get("revision"):
            return
        self.fields["diff_id"].queryset = self.context["revision"].diffs.all()

    @transaction.atomic
    def create(self, validated_data):
        diff = validated_data.get("diff_id", None)
        link_attrs = {
            [issue.path]: {
                "new_for_revision": issue.get("new_for_revision"),
                "in_patch": issue.get("in_patch"),
            }
            for issue in validated_data["issues"]
        }
        # Only create issues that do not exist yet
        issues = Issue.objects.bulk_create(
            [Issue(**values) for values in validated_data["issues"]],
            ignore_conflicts=True,
        )
        # List issues again to ensure ID are synced for creating links
        issues = (
            Issue.objects.filter(path__in=[issue.path for issue in issues])
            # TODO Remove the distinct clause when issues are duplicated (unique path)
            .distinct("path")
            .only("id", "path")
        )
        IssueLink.objects.bulk_create(
            [
                IssueLink(
                    issue_id=issue.id,
                    diff=diff,
                    revision=self.context["revision"],
                    new_for_revision=link_attrs[issue.path]["new_for_revision"],
                    in_patch=link_attrs[issue.path]["in_patch"],
                )
                for issue in issues
            ]
        )
        return {
            "diff_id": diff,
            "issues": issues,
        }


class IssueCheckSerializer(IssueSerializer):
    """
    Serialize an Issue with all the diffs where it has been found.
    Each diff is serialized with its revision's information.
    """

    diffs = DiffLightSerializer(many=True)

    class Meta:
        model = Issue
        fields = IssueSerializer.Meta.fields + ("diffs",)


class IssueCheckStatsSerializer(serializers.Serializer):
    """
    Serialize the usage statistics for each check encountered
    """

    # The view aggregates issues depending on their reference to a repository (via IssueLink M2M)
    repository = serializers.SlugField(source="revisions__head_repository__slug")
    analyzer = serializers.CharField()
    check = serializers.CharField(source="analyzer_check")
    total = serializers.IntegerField()
    publishable = serializers.IntegerField(default=0)

    class Meta:
        model = Issue
        fields = IssueSerializer.Meta.fields + ("repositories",)


class HistoryPointSerializer(serializers.Serializer):
    """
    Serialize a data point for issue checks history graphs
    """

    date = serializers.DateField()
    total = serializers.IntegerField()
