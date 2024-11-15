# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from itertools import groupby

from django.db import transaction
from django.db.models import Q
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
        link_attrs = defaultdict(list)
        # Separate attributes that are specific to the IssueLink M2M
        for issue in validated_data["issues"]:
            link_attrs[issue["hash"]].append(
                {
                    "new_for_revision": issue.pop(
                        "issue_links__new_for_revision", None
                    ),
                    "in_patch": issue.pop("issue_links__in_patch", None),
                    "line": issue.pop("issue_links__line", None),
                    "nb_lines": issue.pop("issue_links__nb_lines", None),
                    "char": issue.pop("issue_links__path", None),
                }
            )
        # Only create issues that do not exist yet
        issues = Issue.objects.bulk_create(
            [Issue(**values) for values in validated_data["issues"]],
            ignore_conflicts=True,
        )
        # List issues again to ensure ID are synced for creating links
        issues_with_links = list(
            Issue.objects.values("issue_links")
            .filter(
                Q(
                    # Issue is new for this diff/revision
                    issue_links__isnull=True,
                )
                | Q(
                    # Issue exists for this diff/revision
                    issue_links__diff=diff,
                    issue_links__revision=self.context["revision"],
                ),
                hash__in=[issue.hash for issue in issues],
            )
            # Needed for re-serialization
            .values(
                "id",
                "hash",
                "analyzer",
                "analyzer_check",
                "path",
                "level",
                "message",
                "issue_links__id",
                "issue_links__new_for_revision",
                "issue_links__in_patch",
                "issue_links__line",
                "issue_links__nb_lines",
                "issue_links__char",
            )
            .iterator()
        )
        # Group existing links by issue, separating attributes from Issue and from IssueLink
        grouped_issues = {
            issue_attributes["hash"]: (
                issue_attributes,
                [
                    {
                        "new_for_revision": i["issue_links__new_for_revision"],
                        "in_patch": i["issue_links__in_patch"],
                        "line": i["issue_links__line"],
                        "nb_lines": i["issue_links__nb_lines"],
                        "char": i["issue_links__char"],
                    }
                    for i in items
                    # Left empty for issues without any fetched link
                    if i["issue_links__id"]
                ],
            )
            for issue_attributes, items in groupby(
                issues_with_links,
                key=lambda issue: {
                    k: v for k, v in issue.items() if not k.startswith("issue_links__")
                },
            )
        }
        # Iterate over the link attributes to identify the entries to create
        output = []
        issue_links_to_create = []
        for issue_hash, links in link_attrs.items():
            existing_issue, existing_links = grouped_issues[issue_hash]
            for link in links:
                # If the link does not exists, create it
                if not any(
                    link.items() <= existing_link.items()
                    for existing_link in existing_links
                ):
                    issue_links_to_create.append(
                        {
                            "issue_id": existing_issue["id"],
                            "diff": diff,
                            "revision": self.context["revision"],
                            **link,
                        }
                    )
                # Set attributes for re-serialization
                output_link = {f"issue_links__{k}": v for k, v in link.items()}
                output_link.update(existing_issue)
                output_link["publishable"] = (
                    link["in_patch"] and existing_issue["level"] == LEVEL_ERROR
                )
                output.append(output_link)
        # Create missing links in bulk
        IssueLink.objects.bulk_create(
            [IssueLink(**attrs) for attrs in issue_links_to_create]
        )

        return {
            "diff_id": diff,
            "issues": output,
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
