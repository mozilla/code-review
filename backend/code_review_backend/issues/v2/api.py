# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.core.exceptions import BadRequest
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.functional import cached_property
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView

from code_review_backend.issues.models import Diff, IssueLink
from code_review_backend.issues.v2.serializers import DiffIssuesSerializer


class IssueList(ListAPIView):
    """
    Returns issues that are linked to a diff, and depending on the selected mode:
    * known: Issues that have also being detected from the base repository (e.g. mozilla-central).
        `previous_diff_id` is always returned as null when listing known issues.
    * unresolved: Issues that were linked to the previous diff of the same parent revision, and are
        still present on the current diff. Filters out issues that are known by the backend.
    * closed: Issues that were listed on the previous diff of the same parent revision, but does
        not exist on the current diff.

    This endpoint does not uses pagination.
    """

    allowed_modes = ["unresolved", "known", "closed"]
    pagination_class = None

    def get_serializer(self, queryset, many=True):
        return DiffIssuesSerializer(
            {
                "previous_diff_id": self.previous_diff and self.previous_diff.id,
                "issues": queryset,
            },
            context=self.get_serializer_context(),
        )

    @cached_property
    def diff(self):
        return get_object_or_404(
            Diff.objects.select_related("revision"), id=self.kwargs["diff_id"]
        )

    @cached_property
    def previous_diff(self):
        if self.mode == "known":
            # No need to search for a previous diff for known issues
            return None
        return (
            self.diff.revision.diffs.filter(created__lt=self.diff.created)
            .order_by("created")
            .last()
        )

    @cached_property
    def mode(self):
        if (mode := self.kwargs["mode"]) not in self.allowed_modes:
            raise ValidationError(
                detail=f"mode argument must be one of {self.allowed_modes}"
            )
        return mode

    def get_queryset(self):
        return getattr(self, f"{self.mode}_issues").filter(**{self.mode: True})

    def distinct_issues(self, qs):
        """
        Convert a list of issue links to unique couples of (issue_id, issue_hash)
        """
        attributes = ("issue_id", "issue__hash")
        return qs.order_by(*attributes).values(*attributes).distinct(*attributes)

    @property
    def known_issues(self):
        return self.distinct_issues(
            self.diff.issue_links.annotate(
                known=Exists(
                    IssueLink.objects.filter(
                        revision__base_repository_id=self.diff.revision.base_repository_id,
                        issue=OuterRef("issue"),
                    )
                )
            )
        )

    @property
    def unresolved_issues(self):
        if not self.previous_diff:
            raise BadRequest("No previous diff was found to compare issues")
        return self.distinct_issues(
            self.known_issues.filter(known=False).annotate(
                unresolved=Exists(
                    IssueLink.objects.filter(
                        diff=self.previous_diff,
                        issue=OuterRef("issue"),
                    )
                )
            )
        )

    @property
    def closed_issues(self):
        if not self.previous_diff:
            raise BadRequest("No previous diff was found to compare issues")
        return self.distinct_issues(
            self.previous_diff.issue_links.annotate(
                closed=~Exists(
                    IssueLink.objects.filter(
                        diff=self.diff,
                        issue=OuterRef("issue"),
                    )
                )
            )
        )


urls = [
    path(
        "diff/<int:diff_id>/issues/<str:mode>/",
        IssueList.as_view(),
        name="issue-list",
    ),
]
