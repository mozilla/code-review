# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.db import transaction
from rest_framework import serializers

from code_review_backend.issues.models import (
    LEVEL_ERROR,
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
    in_patch = serializers.BooleanField(
        source="issue_links__in_patch", allow_null=True, required=False
    )
    new_for_revision = serializers.BooleanField(
        source="issue_links__new_for_revision", allow_null=True, required=False
    )

    line = serializers.IntegerField(
        source="issue_links__line", allow_null=True, required=False
    )
    nb_lines = serializers.IntegerField(
        source="issue_links__nb_lines", allow_null=True, required=False
    )
    char = serializers.IntegerField(
        source="issue_links__char", allow_null=True, required=False
    )

    class Meta:
        model = Issue
        fields = (
            "id",
            "hash",
            "analyzer",
            "path",
            "level",
            "check",
            "message",
            # Attrs coming from IssueLink
            "publishable",
            "in_patch",
            "new_for_revision",
            "line",
            "nb_lines",
            "char",
        )


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


class SingleIssueBulkSerializer(IssueSerializer):
    # Make hash non unique to avoid validation checks
    hash = serializers.CharField(max_length=32)


class IssueBulkSerializer(serializers.Serializer):
    diff_id = serializers.PrimaryKeyRelatedField(
        # Initialized depending on the revision used for the creation
        queryset=Diff.objects.none(),
        style={"base_template": "input.html"},
        required=False,
        allow_null=True,
    )
    issues = SingleIssueBulkSerializer(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context.get("revision"):
            return
        self.fields["diff_id"].queryset = self.context["revision"].diffs.all()

    @transaction.atomic
    def create(self, validated_data):
        diff = validated_data.get("diff_id", None)
        link_attrs = {
            issue["hash"]: {
                "new_for_revision": issue.pop("issue_links__new_for_revision", None),
                "in_patch": issue.pop("issue_links__in_patch", None),
                "line": issue.pop("issue_links__line", None),
                "nb_lines": issue.pop("issue_links__nb_lines", None),
                "char": issue.pop("issue_links__path", None),
            }
            for issue in validated_data["issues"]
        }
        # Create issues that do not exist yet, one by one to reuse ones with a known hash
        issues = []
        for values in validated_data["issues"]:
            issue, _ = Issue.objects.get_or_create(
                hash=values.pop("hash"), defaults=values
            )
            issues.append(issue)
        IssueLink.objects.bulk_create(
            [
                IssueLink(
                    issue_id=issue.id,
                    diff=diff,
                    revision=self.context["revision"],
                    new_for_revision=link_attrs[issue.hash]["new_for_revision"],
                    in_patch=link_attrs[issue.hash]["in_patch"],
                    line=link_attrs[issue.hash]["line"],
                    nb_lines=link_attrs[issue.hash]["nb_lines"],
                    char=link_attrs[issue.hash]["char"],
                )
                for issue in issues
            ]
        )
        # Override attributes that would be fetched after links creation
        for issue in issues:
            issue.issue_links__new_for_revision = link_attrs[issue.hash].get(
                "new_for_revision"
            )
            issue.issue_links__in_patch = link_attrs[issue.hash].get("in_patch")
            issue.issue_links__line = link_attrs[issue.hash].get("line")
            issue.issue_links__nb_lines = link_attrs[issue.hash].get("nb_lines")
            issue.issue_links__char = link_attrs[issue.hash].get("char")
            issue.publishable = (
                issue.issue_links__in_patch and issue.level == LEVEL_ERROR
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
    repository = serializers.SlugField(
        source="issue_links__revision__head_repository__slug"
    )
    analyzer = serializers.CharField()
    check = serializers.CharField(source="analyzer_check")
    total = serializers.IntegerField()
    publishable = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Issue
        fields = IssueSerializer.Meta.fields + ("repositories",)


class HistoryPointSerializer(serializers.Serializer):
    """
    Serialize a data point for issue checks history graphs
    """

    date = serializers.DateField()
    total = serializers.IntegerField()
