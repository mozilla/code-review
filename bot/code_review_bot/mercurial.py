# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import atexit
import fcntl
import io
import os
import tempfile
import time
from datetime import datetime

import hglib
import requests
import structlog
from libmozdata.lando import LandoCommitMapAPI, LandoMissingCommit
from libmozdata.phabricator import PhabricatorPatch

from code_review_bot.vcs import BaseRepository, BaseWorker

logger = structlog.get_logger(__name__)

DEFAULT_AUTHOR = "code review bot <release-mgmt-analysis@mozilla.com>"
# On build failure, check try status until available every 5 minutes and up to 24h
TRY_STATUS_URL = "https://treestatus.prod.lando.prod.cloudops.mozgcp.net/trees/try"
TRY_STATUS_DELAY = 5 * 60
TRY_STATUS_MAX_WAIT = 24 * 60 * 60


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
            logger.info(f"{name}: {line}")

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
        _log_process(proc.stderr, f"{main_cmd} (err)")
        time.sleep(2)

    out, err = proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Mercurial {main_cmd} failure", out=out, err=err, exc_info=True)
        raise hglib.error.CommandError(cmd, proc.returncode, out, err)

    return out


def batch_checkout(repo_url, repo_dir, revision=b"tip", batch_size=100000):
    """
    Helper to clone a mercurial repository using several steps
    to minimize memory footprint and stay below 1Gb of RAM
    It's used on Heroku small dynos, and support restarts
    """
    assert isinstance(revision, bytes)
    assert isinstance(batch_size, int)
    assert batch_size > 1

    logger.info("Batch checkout", url=repo_url, dir=repo_dir, size=batch_size)
    try:
        cmd = hglib.util.cmdbuilder(
            "clone", repo_url, repo_dir, noupdate=True, verbose=True, stream=True
        )
        hg_run(cmd)
        logger.info("Initial clone finished")
    except hglib.error.CommandError as e:
        if e.err.startswith(f"abort: destination '{repo_dir}' is not empty"):
            logger.info("Repository already present, skipping clone")
        else:
            raise

    repo = hglib.open(repo_dir)
    start = max(int(repo.identify(num=True).strip().decode("utf-8")), 1)
    target = int(repo.identify(rev=revision, num=True).strip().decode("utf-8"))
    if start >= target:
        return
    logger.info("Will process checkout in range", start=start, target=target)

    steps = list(range(start, target, batch_size)) + [target]
    for rev in steps:
        logger.info("Moving repo to revision", dir=repo_dir, rev=rev)
        repo.update(rev=rev)


def robust_checkout(
    repo_url,
    checkout_dir,
    sharebase_dir,
    revision=None,
    branch=None,
    repo_upstream_url=None,
):
    if not ((revision is not None) ^ (branch is not None)):
        raise Exception("Set revision XOR branch")

    cmd = hglib.util.cmdbuilder(
        "robustcheckout",
        repo_url,
        checkout_dir,
        purge=True,
        sharebase=sharebase_dir,
        revision=revision,
        branch=branch,
        upstream=repo_upstream_url,
    )
    hg_run(cmd)


class MercurialRepository(BaseRepository):
    """
    A Mercurial repository with its try server credentials
    """

    DEFAULT_REVISION = "default"

    def __init__(self, config, cache_root):
        super().__init__(config, cache_root)
        self.share_base_dir = os.path.join(cache_root, f"{config['name']}-shared")
        self.checkout_mode = config.get("checkout", "batch")
        self.batch_size = config.get("batch_size", 10000)

        # Crash when configuration requests try syntax
        if config.get("try_mode") == "syntax":
            raise Exception("Try syntax mode is deprecated")

        # Write ssh key from secret
        _, self.ssh_key_path = tempfile.mkstemp(suffix=".key")
        with open(self.ssh_key_path, "w") as f:
            f.write(config["ssh_key"])

        # Build ssh conf
        conf = {
            "StrictHostKeyChecking": "no",
            "User": config["ssh_user"],
            "IdentityFile": self.ssh_key_path,
        }
        self.ssh_conf = "ssh {}".format(
            " ".join(f'-o {k}="{v}"' for k, v in conf.items())
        ).encode("utf-8")

        # Remove key when finished
        atexit.register(self.end_of_life)

    def end_of_life(self):
        os.unlink(self.ssh_key_path)
        logger.info("Removed ssh key")

    def clone(self):
        logger.info("Checking out default", repo=self.url, mode=self.checkout_mode)
        if self.checkout_mode == "batch":
            batch_checkout(self.url, self.dir, b"default", self.batch_size)
        elif self.checkout_mode == "robust":
            robust_checkout(self.url, self.dir, self.share_base_dir, branch=b"default")
        else:
            hglib.clone(self.url, self.dir)
        logger.info("Full checkout finished")

        # Setup repo in main process
        self.repo.setcbout(lambda msg: logger.info("Mercurial", stdout=msg))
        self.repo.setcberr(lambda msg: logger.info("Mercurial", stderr=msg))

    @property
    def repo(self):
        """
        Get the repo instance, in case it's None re-open it
        """
        if self._repo is None or self._repo.server is None:
            logger.info(f"Mercurial open {self.dir}")
            self._repo = hglib.open(self.dir)

        return self._repo

    def get_mercurial_base_hash(self, revision):
        """A revision may reference to a Git commit hash instead of Mercurial one.
        The revision can either be a 40 characters full hash or its first 12 characters (short hash).
        A Lando API enables to "convert" the Git hash to a Mercurial hash that can
        be found in the local repository, whatever its length.
        """
        api = LandoCommitMapAPI()
        try:
            commit_map = api.git2hg(revision)
            logger.info(
                "Converted git revision into mercurial through Lando",
                hg=commit_map.hg_hash,
                git=commit_map.git_hash,
            )
            return commit_map.hg_hash
        except LandoMissingCommit:
            logger.warning(
                "No matching revision found on Lando. The default revision will be used instead."
            )
            return self.default_revision

        except Exception as e:
            logger.warning(
                f"Could not convert Git hash to Mercurial hash from Lando: {e}. "
                "The default revision will be used instead."
            )
            return self.default_revision

    def has_revision(self, revision):
        """
        Check if a revision is directly available on this Mercurial repo
        """
        if not revision:
            return False
        try:
            self.repo.identify(revision)
            return True
        except hglib.error.CommandError:
            return False

    def get_base_identifier(self, needed_stack: list[PhabricatorPatch]) -> str:
        """Return the base identifier to apply patches against."""
        if self.use_latest_revision:
            # Use `default` when `use_latest_revision` is `True`.
            return "default"

        # Otherwise use the base/parent revision of first revision in the stack.
        base_rev_hash = needed_stack[0].base_revision
        if self.has_revision(base_rev_hash):
            return base_rev_hash
        else:
            # Base revision may reference a Git hash on new repositories
            return self.get_mercurial_base_hash(base_rev_hash)

    def checkout_base(self, base):
        """Update the local checkout to the base revision"""
        try:
            logger.info(f"Updating repo to revision {base}")
            self.repo.update(rev=base, clean=True)

            # See if the repo is clean
            repo_status = self.repo.status(
                modified=True, added=True, removed=True, deleted=True
            )
            if len(repo_status) != 0:
                logger.warn(
                    "Repo is dirty!",
                    revision=base,
                    repo=self.name,
                    repo_status=repo_status,
                )

        except hglib.error.CommandError:
            raise Exception(f"Failed to update to revision {base}")

        # In this case revision is `base`
        logger.info("Updated repo", revision=base, repo=self.name)

    @staticmethod
    def get_author(commit):
        """Helper to build a mercurial author from Phabricator data"""
        author = commit.get("author")
        if author is None:
            return DEFAULT_AUTHOR
        if author["name"] and author["email"]:
            # Build clean version without quotes
            return f"{author['name']} <{author['email']}>"
        return author["raw"]

    def apply_patch(self, patch, message, commit):
        """Apply a single patch on the local checkout and commit it"""
        user = self.get_author(commit) if commit else DEFAULT_AUTHOR

        patches = io.BytesIO(patch.patch.encode("utf-8"))
        try:
            self.repo.import_(
                patches=patches,
                message=message.encode("utf-8"),
                user=user.encode("utf-8"),
                similarity=95,
            )
        except hglib.error.CommandError as e:
            logger.warning(
                (
                    f"Mercurial command from hglib failed: {e}. "
                    "Retrying with --config ui.patch=patch."
                ),
                phid=patch.phid,
                exc_info=True,
            )
            patches.seek(0)
            # Same method as repo.import_() but with the extra argument "--config ui.patch=patch".
            # https://repo.mercurial-scm.org/python-hglib/file/484b56ac4aec/hglib/client.py#l959
            self.repo.rawcommand(
                hglib.util.cmdbuilder(
                    b"import",
                    message=message.encode("utf-8"),
                    user=user.encode("utf-8"),
                    similarity=95,
                    config="ui.patch=patch",
                    *patches,
                )
            )
            # When using an external patch util mercurial won't automatically handle add/remove/renames
            self.repo.rawcommand(
                hglib.util.cmdbuilder(
                    b"addremove",
                    similarity=95,
                )
            )
        except Exception as e:
            logger.info(
                f"Failed to apply patch: {e}",
                phid=patch.phid,
                exc_info=True,
            )
            raise

    def commit_try_task_config(self, path, message):
        """Commit the try_task_config.json file as the bot"""
        self.repo.add(path.encode("utf-8"))
        self.repo.commit(message=message, user=DEFAULT_AUTHOR)

    def push_to_try(self):
        """
        Push the current tip on remote try repository
        """
        tip = self.repo.tip()
        logger.info("Pushing patches to try", rev=tip.node)
        self.repo.push(
            dest=self.try_url.encode("utf-8"),
            rev=tip.node,
            ssh=self.ssh_conf,
            force=True,
        )
        return tip

    def revision_id(self, tip):
        """Extract the revision identifier from a push_to_try result"""
        return tip.node.decode("utf-8")

    def clean(self):
        """
        Steps to clean the mercurial repo
        """
        logger.info("Remove uncommitted changes")
        self.repo.revert(self.dir.encode("utf-8"), all=True)

        logger.info("Remove all mercurial drafts")
        try:
            cmd = hglib.util.cmdbuilder(
                b"strip", rev=b"roots(outgoing())", force=True, backup=False
            )
            self.repo.rawcommand(cmd)
        except hglib.error.CommandError as e:
            if b"abort: empty revision set" not in e.err:
                raise

        logger.info("Pull updates from remote repo")
        self.repo.pull()


class MercurialWorker(BaseWorker):
    """
    Mercurial worker maintaining several local clones
    """

    VCS_ERROR = hglib.error.CommandError
    VCS_NAME = "Mercurial"
    FAILURE_MODE = "fail:mercurial"
    REPOSITORY_CLASS = MercurialRepository

    ELIGIBLE_RETRY_ERRORS = [
        error.lower()
        for error in [
            "push failed on remote",
            "stream ended unexpectedly",
            "error: EOF occurred in violation of protocol",
        ]
    ]

    def wait_try_available(self):
        """
        Wait until try status is "open"
        On each failure, wait TRY_STATUS_DELAY before retrying up to TRY_STATUS_MAX_WAIT
        """

        def get_status():
            try:
                resp = requests.get(TRY_STATUS_URL)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"An error occurred retrieving try status: {e}")
            else:
                return data.get("result", {}).get("status")

        start = datetime.utcnow()
        while status := get_status() != "open":
            if (datetime.utcnow() - start).seconds >= TRY_STATUS_MAX_WAIT:
                logger.error(
                    f"Try tree status still closed after {TRY_STATUS_MAX_WAIT} seconds, skipping",
                    exc_info=True,
                )
                break
            logger.warning(
                f"Try tree is not actually open (status: {status}), waiting {TRY_STATUS_DELAY} seconds before retrying"
            )
            time.sleep(TRY_STATUS_DELAY)

    def format_error(self, error):
        """Extract a readable error log from a Mercurial exception"""
        error_log = error.err
        if isinstance(error_log, bytes):
            error_log = error_log.decode("utf-8")
        return error_log
