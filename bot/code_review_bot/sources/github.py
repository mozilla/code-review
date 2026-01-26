#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time
from urllib.parse import urljoin

import jwt
import requests


class GithubClient:
    def __init__(self, api_url: str, client_id: str, pem_file_path: str):
        self.api_url = api_url
        self.client_id = client_id
        self.pem_file_path = pem_file_path

    def generate_jwt(self):
        with open(self.pem_file_path) as f:
            signing_key = f.read()

        # https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app#example-using-python-to-generate-a-jwt
        return jwt.encode(
            {
                # Issued at time
                "iat": int(time.time()),
                # JWT expiration time (10 minutes maximum)
                "exp": int(time.time()) + 600,
                # GitHub App's client ID
                "iss": self.client_id,
            },
            signing_key,
            algorithm="RS256",
        )

    def make_request(self, method, path, *, headers={}, **kwargs):
        jwt = self.generate_jwt()
        headers["Authorization"] = f"Bearer {jwt}"
        headers["Accept"] = "application/vnd.github+json"

        url = urljoin(self.api_url, path)
        resp = getattr(requests, method)(
            url,
            headers=headers,
            **kwargs,
        )
        resp.raise_for_status()
        return resp.json()
