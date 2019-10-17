# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from rest_framework import mixins
from rest_framework import routers
from rest_framework import viewsets

from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Revision
from code_review_backend.issues.serializers import DiffSerializer
from code_review_backend.issues.serializers import IssueSerializer
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


class RevisionViewSet(CreateListRetrieveViewSet):
    queryset = Revision.objects.all()
    serializer_class = RevisionSerializer


class DiffViewSet(CreateListRetrieveViewSet):
    queryset = Diff.objects.all()
    serializer_class = DiffSerializer


class IssueViewSet(CreateListRetrieveViewSet):
    serializer_class = IssueSerializer

    def get_queryset(self):
        return Issue.objects.filter(diff_id=self.kwargs["diff_id"])


router = routers.DefaultRouter()
router.register(r"revision", RevisionViewSet)
router.register(r"diff", DiffViewSet)
router.register(r"diff/(?P<diff_id>\d+)/issues", IssueViewSet, basename="issues")
