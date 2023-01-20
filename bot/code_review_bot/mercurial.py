# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from libmozevent.utils import robust_checkout


@contextmanager
def clone_repository(repo_url, branch=b"tip"):
    """
    Clones a repository to a temporary directory using robustcheckout.
    The sharebase is stored in the `checkout-shared` folder, next to the `checkout` returned folder.
    https://github.com/mozilla/libmozevent/blob/fd0b3689c50c3d14ac82302b31115d0046c6e7c8/libmozevent/utils.py#L158
    """
    if not isinstance(branch, bytes):
        # Robustcheckout requires a branch name passed as bytes
        branch = branch.encode()
    with TemporaryDirectory() as temp_path:
        temp_path = Path(temp_path)
        checkout_dir = (temp_path / "checkout").absolute()
        checkout_dir.mkdir()
        robust_checkout(repo_url, str(checkout_dir), branch)
        yield checkout_dir
