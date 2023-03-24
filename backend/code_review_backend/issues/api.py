# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from datetime import date
from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.db.models import Prefetch
from django.db.models import Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import generics
from rest_framework import mixins
from rest_framework import routers
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError

from code_review_backend.issues.compare import detect_new_for_revision
from code_review_backend.issues.models import LEVEL_ERROR
from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import IssueLink
from code_review_backend.issues.models import Repository
from code_review_backend.issues.models import Revision
from code_review_backend.issues.serializers import DiffFullSerializer
from code_review_backend.issues.serializers import DiffSerializer
from code_review_backend.issues.serializers import HistoryPointSerializer
from code_review_backend.issues.serializers import IssueBulkSerializer
from code_review_backend.issues.serializers import IssueCheckSerializer
from code_review_backend.issues.serializers import IssueCheckStatsSerializer
from code_review_backend.issues.serializers import IssueSerializer
from code_review_backend.issues.serializers import RepositorySerializer
from code_review_backend.issues.serializers import RevisionSerializer


class CachedView(object):
    """Helper to bring DRF caching to GET methods"""

    @method_decorator(cache_page(1800))
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


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
        # Required to generate the OpenAPI documentation
        if not self.kwargs.get("revision_id"):
            return Diff.objects.none()
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
            Diff.objects
            # Because of the perf. hit filter issues that are not older than today - 3 months.
            .filter(created__gte=date.today() - timedelta(days=90))
            .prefetch_related(
                "issues",
                "revision",
                "revision__base_repository",
                "revision__head_repository",
                "repository",
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
                Q(revision__base_repository__slug=repository)
                | Q(revision__head_repository__slug=repository)
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
        # Required to generate the OpenAPI documentation
        if not self.kwargs.get("diff_id"):
            return Issue.objects.none()
        diff = get_object_or_404(Diff, id=self.kwargs["diff_id"])
        # No multiple revision should be linked to a single diff
        # but we use the distinct clause to match the DB state.
        return Issue.objects.filter(diffs=diff).distinct()

    @transaction.atomic
    def perform_create(self, serializer):
        # Attach diff to issue created
        # and detect if the issue is new for the revision
        diff = get_object_or_404(Diff, id=self.kwargs["diff_id"])
        issue = serializer.save(
            new_for_revision=detect_new_for_revision(
                diff,
                path=serializer.validated_data["path"],
                hash=serializer.validated_data["hash"],
            ),
        )
        IssueLink.objects.create(
            issue=issue, diff_id=diff.id, revision_id=diff.revision_id
        )


class IssueBulkCreate(generics.CreateAPIView):
    """
    Create multiple issues at once, linked to a mandatory revision and an optional diff.
    """

    serializer_class = IssueBulkSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Required to generate the OpenAPI documentation
        if not self.kwargs.get("revision_id"):
            return context
        revision = get_object_or_404(Revision, id=self.kwargs["revision_id"])
        context["revision"] = revision
        return context


class IssueCheckDetails(CachedView, generics.ListAPIView):
    """
    List all the issues found by a specific analyzer check in a repository
    """

    serializer_class = IssueCheckSerializer

    def get_queryset(self):
        repo = self.kwargs["repository"]

        queryset = (
            Issue.objects.filter(revisions__head_repository__slug=repo)
            .filter(analyzer=self.kwargs["analyzer"])
            .filter(analyzer_check=self.kwargs["check"])
            .prefetch_related(
                "diffs__repository",
                Prefetch(
                    "diffs__revision",
                    queryset=Revision.objects.select_related(
                        "base_repository", "head_repository"
                    ),
                ),
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

        return queryset.distinct()


class IssueCheckStats(CachedView, generics.ListAPIView):
    """
    List all analyzer checks per repository aggregated with
    their total number of issues
    """

    serializer_class = IssueCheckStatsSerializer

    def get_queryset(self):
        queryset = (
            Issue.objects.values(
                "revisions__head_repository__slug", "analyzer", "analyzer_check"
            )
            # We want to count distinct issues because they can be referenced on multiple diffs
            .annotate(total=Count("id", distinct=True))
            .annotate(
                publishable=Count("id", filter=Q(in_patch=True) | Q(level=LEVEL_ERROR))
            )
            .distinct("revisions__head_repository__slug", "analyzer", "analyzer_check")
        )

        # Filter issues by date
        since = self.request.query_params.get("since")
        if since is not None:
            try:
                since = datetime.strptime(since, "%Y-%m-%d").date()
            except ValueError:
                raise APIException(detail="invalid since date - should be YYYY-MM-DD")
        else:
            # Because of the perf. hit filter, issues that are not older than today - 3 months.
            since = date.today() - timedelta(days=90)

        queryset = queryset.filter(revisions__created__gte=since).distinct()

        return queryset.order_by(
            "-total", "revisions__head_repository__slug", "analyzer", "analyzer_check"
        )


class IssueCheckHistory(CachedView, generics.ListAPIView):
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
            queryset = queryset.filter(
                Q(diffs__revision__base_repository__slug=repository)
                | Q(diffs__revision__head_repository__slug=repository)
            )

        # Filter by analyzer
        analyzer = self.request.query_params.get("analyzer")
        if analyzer:
            queryset = queryset.filter(analyzer=analyzer)

        # Filter by check
        check = self.request.query_params.get("check")
        if check:
            queryset = queryset.filter(analyzer_check=check)

        # Filter by date
        since = self.request.query_params.get("since")
        if since is not None:
            try:
                since = datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                raise APIException(detail="invalid since date - should be YYYY-MM-DD")

            if "postgresql" in settings.DATABASES["default"]["ENGINE"]:
                # Use a specific WHERE clause to compare the creation date.
                # Casting the date as its natural data type (timestamptz) allow Postgres to perform an
                # index scan on small data ranges (depending on available memory), which is much faster.
                # Overall performance is improved in practice, even if the planned cost is higher when
                # aggregating on the whole table.
                since_date = since.strftime("%Y-%m-%d")
                queryset = queryset.extra(
                    where=[f"created::timestamptz >= '{since_date}'::timestamptz"]
                )
            else:
                queryset = queryset.filter(date__gte=since.date())

        return queryset.order_by("date").distinct()


class IssueList(generics.ListAPIView):
    serializer_class = IssueSerializer

    def get_queryset(self):
        qs = Issue.objects.all()

        errors = defaultdict(list)
        repo_slug = self.kwargs["repo_slug"]
        try:
            repo = Repository.objects.get(slug=repo_slug)
        except Repository.DoesNotExist:
            errors["repo_slug"].append(
                "invalid repo_slug path argument - No repository match this slug"
            )
        else:
            qs = qs.filter(revisions__head_repository=repo)

        # Always filter by path when the parameter is set
        if path := self.request.query_params.get("path"):
            qs = qs.filter(path=path)

        date_revision = None
        if date := self.request.query_params.get("date"):
            try:
                date = datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)
            except ValueError:
                errors["date"].append("invalid date - should be YYYY-MM-DD")
            else:
                # Look for a revision matching this date, going back to 2 days maximum
                date_revision = (
                    Revision.objects.filter(
                        created__gte=date - timedelta(2),
                        created__lt=date,
                    )
                    .order_by("-created")
                    .first()
                )

        revision = self.request.query_params.get("revision")
        if revision and not revision.isdecimal():
            errors["revision"].append("invalid revision - should be a number")

        if errors:
            raise ValidationError(errors)

        # Only use the revision filter in case some issues are found
        if revision and qs.filter(revisions__id=revision).exists():
            qs = qs.filter(revisions__id=revision)
        elif revision and not date_revision:
            qs = Issue.objects.none()
        # Defaults to filtering by the revision closest to the given date
        elif date_revision:
            qs = qs.filter(revisions=date_revision)

        return qs.order_by("created").distinct()


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
    path(
        "revision/<int:revision_id>/issues/",
        IssueBulkCreate.as_view(),
        name="revision-issues-bulk",
    ),
    path("check/stats/", IssueCheckStats.as_view(), name="issue-checks-stats"),
    path("check/history/", IssueCheckHistory.as_view(), name="issue-checks-history"),
    path(
        "check/<str:repository>/<str:analyzer>/<path:check>/",
        IssueCheckDetails.as_view(),
        name="issue-check-details",
    ),
    path("issues/<slug:repo_slug>/", IssueList.as_view(), name="repository-issues"),
]
