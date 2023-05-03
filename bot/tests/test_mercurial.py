# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from pathlib import PosixPath

from code_review_bot import mercurial


class STDOutputMock:
    def fileno(self):
        return 4

    content = ""


class PopenMock:
    stdout = STDOutputMock()
    stderr = STDOutputMock()
    returncode = 0

    def poll(self):
        return True

    def communicate(self):
        out = self.stdout.content = "Hello world"
        err = self.stderr.content = "An error occurred"
        return out, err

    def __call__(self, command):
        self.command = command
        return self


def test_hg_run(monkeypatch):
    popen_mock = PopenMock()
    monkeypatch.setattr("hglib.util.popen", popen_mock)
    mercurial.hg_run(["checkout", "https://hg.repo/", "--test"])
    assert popen_mock.command == ["hg", "checkout", "https://hg.repo/", "--test"]
    assert popen_mock.stdout.content == "Hello world"
    assert popen_mock.stderr.content == "An error occurred"


def test_clone_repository_context_manager(monkeypatch):
    popen_mock = PopenMock()
    monkeypatch.setattr("hglib.util.popen", popen_mock)

    with mercurial.clone_repository(
        "https://hg.repo/", branch="default"
    ) as repo_checkout:
        assert isinstance(repo_checkout, PosixPath)
        assert str(repo_checkout.absolute()).startswith("/tmp/")
        assert repo_checkout.stem == "checkout"
        parent_folder = repo_checkout.parent.absolute()
        assert parent_folder.exists()
        assert str(parent_folder) != "/tmp"

    assert popen_mock.command == [
        "hg",
        "robustcheckout",
        b"--purge",
        f"--sharebase={parent_folder}/shared".encode(),
        b"--branch=default",
        b"--",
        "https://hg.repo/",
        str(repo_checkout),
    ]
    assert not parent_folder.exists()
