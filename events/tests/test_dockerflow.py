# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
from libmozevent.web import WebServer

from code_review_events.workflow import BASE_DIR

VERSION_PATH = f"{BASE_DIR}/version.json"


@pytest.fixture
def webserver():
    webserver = WebServer(None, version_path=VERSION_PATH)
    webserver.start()
    yield webserver
    webserver.stop()


async def test_get_version(aiohttp_client, webserver):
    client = await aiohttp_client(webserver.app)
    response = await client.get("/__version__")
    assert response.status == 200

    with open(VERSION_PATH, "r") as version_file:
        assert await response.json() == json.loads(version_file.read())


async def test_get_heartbeat(aiohttp_client, webserver):
    client = await aiohttp_client(webserver.app)
    response = await client.get("/__heartbeat__")
    assert response.status == 200


async def test_get_lbheartbeat(aiohttp_client, webserver):
    client = await aiohttp_client(webserver.app)
    response = await client.get("/__lbheartbeat__")
    assert response.status == 200
