# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.conf import settings
from rest_framework.test import APITestCase

from code_review_backend.issues.models import Repository
from code_review_backend.issues.models import Revision


class RevisionAPITestCase(APITestCase):
    def setUp(self):
        self.repo = Repository.objects.create(
            id=1, phid="PHID-REPO-xxx", slug="myrepo", url="http://repo.test/myrepo"
        )

    def test_phabricator_url(self):
        rev = Revision.objects.create(
            id=12, phid="PHID-REV-12345", repository=self.repo
        )

        # Default settings
        self.assertEqual(
            rev.phabricator_url, "https://phabricator.services.mozilla.com/D12"
        )

        # Override host with /api
        settings.PHABRICATOR_HOST = "http://phab.test/api"
        self.assertEqual(rev.phabricator_url, "http://phab.test/D12")

        # Override host with complex url
        settings.PHABRICATOR_HOST = "http://anotherphab.test/api123/?custom"
        self.assertEqual(rev.phabricator_url, "http://anotherphab.test/D12")
