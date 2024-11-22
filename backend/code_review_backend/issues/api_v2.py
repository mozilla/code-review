# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf import settings
from django.db.models import Exists, OuterRef, Value
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.functional import cached_property
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView

from code_review_backend.issues.models import Diff, IssueLink
from code_review_backend.issues.serializers_v2 import IssueLinkHashSerializer


class IssueList(ListAPIView):
    serializer_class = IssueLinkHashSerializer
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
        return getattr(self, f"{self.mode}_issues").filter(**{self.mode: True})

    def distinct_issues(self, qs):
        """
        Convert a list of issue links to unique couples of (issue_id, issue_hash)
        """
        attributes = ("issue_id", "issue__hash")
        if "postgresql" in settings.DATABASES["default"]["ENGINE"]:
            return qs.order_by(*attributes).values(*attributes).distinct(*attributes)
        return qs.order_by(*attributes).values(*attributes).distinct()

    @property
    def known_issues(self):
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
            )
        )

    @property
    def unresolved_issues(self):
        """
        Issues that were linked to the previous diff of the same
        parent revision, and are still present on the current diff.
        Filters out issues that are known by the backend.
        """
        previous_diff = (
            self.diff.revision.diffs.filter(created__lt=self.diff.created)
            .order_by("created")
            .last()
        )
        if not previous_diff:
            return IssueLink.objects.none().annotate(unresolved=Value("True"))
        return self.distinct_issues(
            self.known_issues.filter(known=False).annotate(
                unresolved=Exists(
                    IssueLink.objects.filter(
                        diff=previous_diff,
                        issue=OuterRef("issue"),
                    )
                )
            )
        )

    @property
    def closed_issues(self):
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
            return IssueLink.objects.none().annotate(closed=Value("True"))
        return self.distinct_issues(
            previous_diff.issue_links.annotate(
                closed=~Exists(
                    IssueLink.objects.filter(
                        diff=self.diff,
                        issue=OuterRef("issue"),
                    )
                )
            )
        )


urls = [
    # Prevails on the generic issues endpoint
    path(
        "diff/<int:diff_id>/issues/<str:mode>/",
        IssueList.as_view(),
        name="issue-list",
    ),
]
