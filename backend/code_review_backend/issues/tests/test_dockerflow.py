# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json

from django.conf import settings
from django.test import TestCase


class DockerflowEndpointsTestCase(TestCase):
    def setUp(self):
        self.old_setting = settings.DEBUG

    def tearDown(self):
        settings.DEBUG = self.old_setting

    def test_get_version(self):
        response = self.client.get("/__version__")
        self.assertEqual(response.status_code, 200)

        with open(f"{settings.BASE_DIR}/version.json") as version_file:
            self.assertEqual(response.json(), json.loads(version_file.read()))

    def test_get_heartbeat_debug(self):
        settings.DEBUG = True

        response = self.client.get("/__heartbeat__")
        self.assertEqual(response.status_code, 200)

        # In DEBUG mode, we can retrieve checks details
        heartbeat = response.json()
        self.assertEqual(heartbeat["status"], "ok")
        self.assertTrue("checks" in heartbeat)
        self.assertTrue("details" in heartbeat)

    def test_get_heartbeat(self):
        settings.DEBUG = False

        response = self.client.get("/__heartbeat__")
        self.assertEqual(response.status_code, 200)

        # When DEBUG is False, we can't retrieve checks details and the status is certainly
        # equal to "warning" because of the deployment checks that are added:
        # https://github.com/mozilla-services/python-dockerflow/blob/e316f0c5f0aa6d176a6d08d1f568f83658b51339/src/dockerflow/django/views.py#L45
        self.assertEqual(response.json(), {"status": "warning"})

    def test_get_lbheartbeat(self):
        response = self.client.get("/__lbheartbeat__")
        self.assertEqual(response.status_code, 200)
