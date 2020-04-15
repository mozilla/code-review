# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime

from django.db.models import Count
from django.db.models import Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework import generics
from rest_framework import mixins
from rest_framework import routers
from rest_framework import viewsets
from rest_framework.exceptions import APIException

from code_review_backend.issues.compare import detect_new_for_revision
from code_review_backend.issues.models import LEVEL_ERROR
from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Repository
from code_review_backend.issues.models import Revision
from code_review_backend.issues.serializers import DiffFullSerializer
from code_review_backend.issues.serializers import DiffSerializer
from code_review_backend.issues.serializers import HistoryPointSerializer
from code_review_backend.issues.serializers import IssueCheckSerializer
from code_review_backend.issues.serializers import IssueCheckStatsSerializer
from code_review_backend.issues.serializers import IssueSerializer
from code_review_backend.issues.serializers import RepositorySerializer
from code_review_backend.issues.serializers import RevisionSerializer


class CreateListRetrieveViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    A viewset that allows creation, listing and retrieval of Model instances
    From https://www.django-rest-framework.org/api-guide/viewsets/#custom-viewset-base-classes
    """


class RepositoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Repository.objects.all().order_by("slug")
    serializer_class = RepositorySerializer


class RevisionViewSet(CreateListRetrieveViewSet):
    """
    Manages revisions
    """

    queryset = Revision.objects.all()
    serializer_class = RevisionSerializer


class RevisionDiffViewSet(CreateListRetrieveViewSet):
    """
    Manages diffs in a revision (allow creation)
    """

    serializer_class = DiffSerializer

    def get_queryset(self):
        return Diff.objects.filter(revision_id=self.kwargs["revision_id"])

    def perform_create(self, serializer):
        # Attach revision to diff created
        revision = get_object_or_404(Revision, id=self.kwargs["revision_id"])
        serializer.save(revision=revision)


class DiffViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve diffs with detailed revision information
    """

    serializer_class = DiffFullSerializer

    def get_queryset(self):
        diffs = (
            Diff.objects.all()
            .prefetch_related(
                "issues", "revision", "revision__repository", "repository"
            )
            .annotate(nb_issues=Count("issues"))
            .annotate(nb_errors=Count("issues", filter=Q(issues__level="error")))
            .annotate(nb_warnings=Count("issues", filter=Q(issues__level="warning")))
            .annotate(
                nb_issues_publishable=Count(
                    "issues",
                    filter=Q(issues__in_patch=True) | Q(issues__level=LEVEL_ERROR),
                )
            )
            .order_by("-id")
        )

        # Filter by repository
        repository = self.request.query_params.get("repository")
        if repository is not None:
            diffs = diffs.filter(
                Q(revision__repository__slug=repository)
                | Q(repository__slug=repository)
            )

        # Filter by text search query
        query = self.request.query_params.get("search")
        if query is not None:
            search_query = (
                Q(id__icontains=query)
                | Q(revision__id__icontains=query)
                | Q(revision__bugzilla_id__icontains=query)
                | Q(revision__title__icontains=query)
            )
            diffs = diffs.filter(search_query)

        # Filter by issues types
        issues = self.request.query_params.get("issues")
        if issues == "any":
            diffs = diffs.filter(nb_issues__gt=0)
        elif issues == "publishable":
            diffs = diffs.filter(nb_issues_publishable__gt=0)
        elif issues == "no":
            diffs = diffs.filter(nb_issues=0)

        return diffs


class IssueViewSet(viewsets.ModelViewSet):
    serializer_class = IssueSerializer

    def get_queryset(self):
        return Issue.objects.filter(diff_id=Diff.objects.get(pk=self.kwargs["diff_id"]))

    def perform_create(self, serializer):
        # Attach diff to issue created
        # and detect if the issue is new for the revision
        diff = get_object_or_404(Diff, id=self.kwargs["diff_id"])
        serializer.save(
            diff=diff,
            new_for_revision=detect_new_for_revision(
                diff,
                path=serializer.validated_data["path"],
                hash=serializer.validated_data["hash"],
            ),
        )


class IssueCheckDetails(generics.ListAPIView):
    """
    List all the issues found by a specific analyzer check in a repository
    """

    serializer_class = IssueCheckSerializer

    def get_queryset(self):
        repo = self.kwargs["repository"]

        queryset = (
            Issue.objects.filter(
                Q(diff__repository__slug=repo)
                | Q(diff__revision__repository__slug=repo)
            )
            .filter(analyzer=self.kwargs["analyzer"])
            .filter(check=self.kwargs["check"])
            .prefetch_related(
                "diff",
                "diff__repository",
                "diff__revision",
                "diff__revision__repository",
            )
            .order_by("-created")
        )

        # Display only publishable issues by default
        publishable = self.request.query_params.get("publishable", "true").lower()
        _filter = Q(in_patch=True) | Q(level=LEVEL_ERROR)
        if publishable == "true":
            queryset = queryset.filter(_filter)
        elif publishable == "false":
            queryset = queryset.exclude(_filter)
        elif publishable != "all":
            raise APIException(detail="publishable can only be true, false or all")

        # Filter issues by date
        since = self.request.query_params.get("since")
        if since is not None:
            try:
                since = datetime.strptime(since, "%Y-%m-%d").date()
            except ValueError:
                raise APIException(detail="invalid since date - should be YYYY-MM-DD")
            queryset = queryset.filter(created__gte=since)

        return queryset


class IssueCheckStats(generics.ListAPIView):
    """
    List all analyzer checks per repository aggregated with
    their total number of issues
    """

    serializer_class = IssueCheckStatsSerializer

    def get_queryset(self):

        queryset = (
            Issue.objects.values(
                "analyzer", "check", "diff__revision__repository__slug"
            )
            .annotate(total=Count("id"))
            .annotate(
                publishable=Count("id", filter=Q(in_patch=True) | Q(level=LEVEL_ERROR))
            )
            .prefetch_related("diff", "diff_revision", "diff__revision__repository")
        )

        # Filter issues by date
        since = self.request.query_params.get("since")
        if since is not None:
            try:
                since = datetime.strptime(since, "%Y-%m-%d").date()
            except ValueError:
                raise APIException(detail="invalid since date - should be YYYY-MM-DD")
            queryset = queryset.filter(diff__created__gte=since)

        return queryset.order_by("-total")


class IssueCheckHistory(generics.ListAPIView):
    """
    Historical usage per day of an issue checks
    * globally
    * per repository
    * per analyzer
    * per check
    """

    serializer_class = HistoryPointSerializer

    # For ease of use, the history is available without pagination
    # as the SQL request should be always fast to calculate
    pagination_class = None

    def get_queryset(self):

        # Count all the issues per day
        queryset = (
            Issue.objects.annotate(date=TruncDate("created"))
            .values("date")
            .annotate(total=Count("id"))
        )

        # Filter by repository
        repository = self.request.query_params.get("repository")
        if repository:
            queryset = queryset.filter(diff__revision__repository__slug=repository)

        # Filter by analyzer
        analyzer = self.request.query_params.get("analyzer")
        if analyzer:
            queryset = queryset.filter(analyzer=analyzer)

        # Filter by check
        check = self.request.query_params.get("check")
        if check:
            queryset = queryset.filter(check=check)

        # Filter by date
        since = self.request.query_params.get("since")
        if since is not None:
            try:
                since = datetime.strptime(since, "%Y-%m-%d").date()
            except ValueError:
                raise APIException(detail="invalid since date - should be YYYY-MM-DD")
            queryset = queryset.filter(date__gte=since)

        return queryset.order_by("date")


# Build exposed urls for the API
router = routers.DefaultRouter()
router.register(r"repository", RepositoryViewSet)
router.register(r"revision", RevisionViewSet)
router.register(
    r"revision/(?P<revision_id>\d+)/diffs",
    RevisionDiffViewSet,
    basename="revision-diffs",
)
router.register(r"diff", DiffViewSet, basename="diffs")
router.register(r"diff/(?P<diff_id>\d+)/issues", IssueViewSet, basename="issues")
urls = router.urls + [
    path("check/stats/", IssueCheckStats.as_view(), name="issue-checks-stats"),
    path("check/history/", IssueCheckHistory.as_view(), name="issue-checks-history"),
    path(
        "check/<str:repository>/<str:analyzer>/<str:check>/",
        IssueCheckDetails.as_view(),
        name="issue-check-details",
    ),
]
