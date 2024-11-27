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
        self.assertEqual(Repository.objects.count(), 5)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {
                "count": 5,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": 102,
                        "slug": "autoland",
                        "url": "https://hg.mozilla.org/integration/autoland",
                    },
                    {
                        "id": 1,
                        "slug": "mozilla-central",
                        "url": "https://hg.mozilla.org/mozilla-central",
                    },
                    {
                        "id": 8,
                        "slug": "nss",
                        "url": "https://hg.mozilla.org/projects/nss",
                    },
                    {
                        "id": 101,
                        "slug": "nss-try",
                        "url": "https://hg.mozilla.org/projects/nss-try",
                    },
                    {
                        "id": 100,
                        "slug": "try",
                        "url": "https://hg.mozilla.org/try",
                    },
                ],
            },
        )
