# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

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


def test_robustcheckout(monkeypatch):
    popen_mock = PopenMock()
    monkeypatch.setattr("hglib.util.popen", popen_mock)

    mercurial.robust_checkout(
        repo_url="https://hg.repo/try",
        repo_upstream_url="https://hg.repo/mc",
        revision="deadbeef1234",
        checkout_dir="/tmp/checkout",
        sharebase_dir="/tmp/shared",
    )

    assert popen_mock.command == [
        "hg",
        "robustcheckout",
        b"--purge",
        b"--sharebase=/tmp/shared",
        b"--revision=deadbeef1234",
        b"--upstream=https://hg.repo/mc",
        b"--",
        "https://hg.repo/try",
        "/tmp/checkout",
    ]
