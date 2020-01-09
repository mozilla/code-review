# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.test import TestCase

from code_review_backend.issues.models import LEVEL_ERROR
from code_review_backend.issues.models import LEVEL_WARNING
from code_review_backend.issues.models import Issue


class IssueTestCase(TestCase):
    def test_publishable(self):

        # A warning is not publishable
        issue = Issue.objects.create(path="some/file", line=12, level=LEVEL_WARNING)
        self.assertFalse(issue.publishable)

        # An error is publishable
        issue = Issue.objects.create(path="some/file", line=12, level=LEVEL_ERROR)
        self.assertTrue(issue.publishable)

        # A warning in a patch is publishable
        issue = Issue.objects.create(
            path="some/file", line=12, level=LEVEL_WARNING, in_patch=True
        )
        self.assertTrue(issue.publishable)

        # An error in a patch is publishable
        issue = Issue.objects.create(
            path="some/file", line=12, level=LEVEL_ERROR, in_patch=True
        )
        self.assertTrue(issue.publishable)
