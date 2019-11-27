# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from rest_framework import status
from rest_framework.test import APITestCase

from code_review_backend.issues.models import Repository


class RepositoryAPITestCase(APITestCase):
    fixtures = ["fixtures/repositories.json"]

    def test_list_repositories(self):
        """
        Check we can list all repositories in database
        """
        response = self.client.get("/v1/repository/")
        self.assertEqual(Repository.objects.count(), 4)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {
                "count": 4,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": 1,
                        "phid": "PHID-REPO-saax4qdxlbbhahhp2kg5",
                        "slug": "mozilla-central",
                        "url": "https://hg.mozilla.org/mozilla-central",
                    },
                    {
                        "id": 8,
                        "phid": "PHID-REPO-3lrloqw4qf6fluy2a5ni",
                        "slug": "nss",
                        "url": "https://hg.mozilla.org/projects/nss",
                    },
                    {
                        "id": 101,
                        "phid": None,
                        "slug": "nss-try",
                        "url": "https://hg.mozilla.org/projects/nss-try",
                    },
                    {
                        "id": 100,
                        "phid": None,
                        "slug": "try",
                        "url": "https://hg.mozilla.org/try",
                    },
                ],
            },
        )
