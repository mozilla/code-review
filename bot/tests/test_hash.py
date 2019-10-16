# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib

from code_review_bot.tasks.lint import MozLintIssue


def test_build_hash(mock_revision, mock_hgmo):
    """
    Test build hash algorithm
    """
    # Hardcode revision & repo
    mock_revision.repository = "test-try"
    mock_revision.mercurial_revision = "deadbeef1234"

    issue = MozLintIssue(
        "mock-analyzer-eslint",
        "path/to/file.cpp",
        42,
        "error",
        123,
        "eslint",
        "A random & fake linting issue",
        "EXXX",
        mock_revision,
    )
    assert (
        str(issue) == "mock-analyzer-eslint issue EXXX@error path/to/file.cpp line 123"
    )

    # Check the mock file retrieval for that file
    raw_file = mock_revision.load_file(issue.path)
    assert raw_file == "\n".join(
        f"test-try:deadbeef1234:path/to/file.cpp:{i+1}" for i in range(1000)
    )

    # Build hash in the unit test by re-creating the payload
    payload = "mock-analyzer-eslint:path/to/file.cpp:error:EXXX:{}:test-try:deadbeef1234:path/to/file.cpp:123"
    hash_check = hashlib.md5(payload.encode("utf-8")).hexdigest()
    assert hash_check == "045f57ef8ee111d0c8c475bd7a617564" == issue.build_hash()
