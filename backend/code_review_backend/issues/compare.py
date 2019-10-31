# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Issue


def detect_new_for_revision(diff: Diff, path: str, hash: str) -> bool:
    """Detect if an issue identified by its path and hash are new for a revision, from its diff"""
    assert diff is not None, "Missing diff"
    return not Issue.objects.filter(
        diff__revision_id=diff.revision_id, diff_id__lt=diff.id, path=path, hash=hash
    ).exists()
