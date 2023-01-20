# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import hglib
import structlog

logger = structlog.get_logger(__name__)


def hg_run(cmd):
    """
    Run a mercurial command without an hglib instance
    Useful for initial custom clones
    Redirects stdout & stderr to python's logger

    This code has been copied from the libmozevent library
    https://github.com/mozilla/libmozevent/blob/fd0b3689c50c3d14ac82302b31115d0046c6e7c8/libmozevent/utils.py#L77
    """

    def _log_process(output, name):
        # Read and display every line
        out = output.read()
        if out is None:
            return
        text = filter(None, out.decode("utf-8").splitlines())
        for line in text:
            logger.info("{}: {}".format(name, line))

    # Start process
    main_cmd = cmd[0]
    proc = hglib.util.popen([hglib.HGPATH] + cmd)

    # Set process outputs as non blocking
    for output in (proc.stdout, proc.stderr):
        fcntl.fcntl(
            output.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(output, fcntl.F_GETFL) | os.O_NONBLOCK,
        )

    while proc.poll() is None:
        _log_process(proc.stdout, main_cmd)
        _log_process(proc.stderr, "{} (err)".format(main_cmd))
        time.sleep(2)

    out, err = proc.communicate()
    if proc.returncode != 0:
        logger.error(
            "Mercurial {} failure".format(main_cmd), out=out, err=err, exc_info=True
        )
        raise hglib.error.CommandError(cmd, proc.returncode, out, err)

    return out


def robust_checkout(repo_url, checkout_dir, sharebase_dir, branch):
    cmd = hglib.util.cmdbuilder(
        "robustcheckout",
        repo_url,
        checkout_dir,
        purge=True,
        sharebase=sharebase_dir,
        branch=branch,
    )
    hg_run(cmd)


@contextmanager
def clone_repository(repo_url, branch="tip"):
    """
    Clones a repository to a temporary directory using robustcheckout.
    """
    with TemporaryDirectory() as temp_path:
        temp_path = Path(temp_path)
        checkout_dir = (temp_path / "checkout").absolute()
        checkout_dir.mkdir()
        sharebase_dir = (temp_path / "shared").absolute()
        sharebase_dir.mkdir()
        robust_checkout(repo_url, str(checkout_dir), str(sharebase_dir), branch)
        yield checkout_dir
