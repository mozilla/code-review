# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.functional import cached_property
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView

from code_review_backend.issues.models import Diff, IssueLink
from code_review_backend.issues.serializers import IssueHashSerializer


class IssueList(ListAPIView):
    serializer_class = IssueHashSerializer
    allowed_modes = ["unresolved", "known", "closed"]

    @cached_property
    def diff(self):
        return get_object_or_404(
            Diff.objects.select_related("revision"), id=self.kwargs["diff_id"]
        )

    @cached_property
    def mode(self):
        if (mode := self.kwargs["mode"]) not in self.allowed_modes:
            raise ValidationError(
                detail=f"mode argument must be one of {self.allowed_modes}"
            )
        return mode

    def get_queryset(self):
        return getattr(self, f"get_{self.mode}")()

    def distinct_issues(self, qs):
        """
        Convert a list of issue links to unique couples of (issue_id, issue_hash)
        """
        attributes = ("issue_id", "issue__hash")
        return qs.order_by(*attributes).values_list(*attributes).distinct()

    def get_unresolved(self):
        """
        Issues that were linked to a previous diff of the same
        parent revision, and are still present on the current diff.
        """
        return self.distinct_issues(
            self.diff.revision.issue_links.annotate(
                unresolved=Exists(
                    IssueLink.objects.exclude(diff=self.diff).filter(
                        revision=self.diff.revision,
                        issue=OuterRef("issue"),
                    )
                )
            ).filter(unresolved=True)
        )

    def get_known(self):
        """
        Issues that have also being detected from mozilla-central.
        """
        return self.distinct_issues(
            self.diff.issue_links.annotate(
                known=Exists(
                    IssueLink.objects.filter(
                        revision__base_repository__slug="mozilla-central",
                        issue=OuterRef("issue"),
                    )
                )
            ).filter(known=True)
        )

    def get_closed(self):
        """
        Issues that were listed on the previous diff of the same
        parent revision, but does not exist on the current diff.
        """
        # Retrieve the previous diff
        previous_diff = (
            self.diff.revision.diffs.filter(created__lt=self.diff.created)
            .order_by("created")
            .last()
        )
        if not previous_diff:
            return []
        return self.distinct_issues(
            previous_diff.issue_links.annotate(
                closed=Exists(
                    IssueLink.objects.filter(
                        diff=self.diff,
                        issue=OuterRef("issue"),
                    )
                )
            ).filter(closed=True)
        )


urls = [
    # Prevails on the generic issues endpoint
    path(
        "diff/<int:diff_id>/issues/<str:mode>/",
        IssueList.as_view(),
        name="issue-list",
    ),
]
