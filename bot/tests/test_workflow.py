# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest import mock
from urllib.parse import unquote_plus

import pytest
import responses
from libmozdata.phabricator import BuildState, ConduitError
from structlog.testing import capture_logs

from code_review_bot import Level
from code_review_bot.analysis import AnalysisMode
from code_review_bot.config import Settings, TaskCluster, settings
from code_review_bot.revisions import PhabricatorRevision
from code_review_bot.tasks.build import BuildIssue, BuildTask
from code_review_bot.tasks.clang_format import ClangFormatIssue, ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyTask
from code_review_bot.tasks.clang_tidy_external import ExternalTidyTask
from code_review_bot.tasks.docupload import DocUploadTask
from code_review_bot.tasks.lint import MozLintIssue, MozLintTask
from code_review_bot.tasks.tgdiff import TaskGraphDiffTask


@pytest.mark.parametrize(
    "task_name, result, on_autoland",
    [
        ("source-test-clang-tidy", ClangTidyTask, False),
        ("source-test-clang-tidy", ClangTidyTask, True),
        ("source-test-clang-external", ExternalTidyTask, False),
        ("source-test-clang-external", ExternalTidyTask, True),
        ("source-test-mozlint-eslint", MozLintTask, False),
        ("source-test-mozlint-eslint", MozLintTask, True),
        ("source-test-mozlint-whatever", MozLintTask, False),
        ("source-test-mozlint-whatever", MozLintTask, True),
        ("source-test-clang-format", ClangFormatTask, False),
        ("source-test-clang-format", ClangFormatTask, True),
        ("source-test-doc-upload", DocUploadTask, False),
        ("source-test-doc-upload", DocUploadTask, True),
        ("source-test-taskgraph-diff", TaskGraphDiffTask, False),
        ("source-test-taskgraph-diff", TaskGraphDiffTask, True),
        ("source-test-unsupported", None, False),
        ("source-test-unsupported", None, True),
        ("build-linux64/opt", BuildTask, False),
        ("build-linux64/opt", BuildTask, True),
        ("build-docker-image-debian12-base", None, False),
        ("build-docker-image-debian12-base", None, True),
    ],
)
def test_build_task(task_name, result, on_autoland, mock_config, mock_workflow):
    """
    Test the build_task method with different task payloads
    """
    # Setup autoland id
    mock_config.autoland_task_id = "someTaskId" if on_autoland else None
    mock_config.autoland_group_id = "someGroupId" if on_autoland else None

    task_status = {
        "task": {"metadata": {"name": task_name}},
        "status": {"taskId": "someTaskId"},
    }

    # Check exceptions thrown
    if result is Exception:
        with pytest.raises(Exception) as e:
            mock_workflow.build_task(task_status)
        assert str(e.value) == f"Unsupported task {task_name}"
        return

    # Normal cases
    task = mock_workflow.build_task(task_status)
    if result is None:
        assert task is None
    else:
        assert isinstance(task, result)


def test_find_issues_doc_upload_both_issues_and_notice(mock_workflow, mock_revision):
    """
    A source-test-doc-upload task both reports issues found in its
    code-review issues.json artifact, and builds a documentation preview
    notice from its doc artifacts (DocUploadTask now supports both, see #3488).
    """
    mock_revision.files = ["docs/folderA/index.rst"]

    mock_workflow.setup_mock_tasks(
        {
            "remoteTryTask": {
                "dependencies": ["doc-upload-task"],
                "name": "code-review-issues",
            },
            "doc-upload-task": {
                "name": "source-test-doc-upload",
                "artifacts": {
                    "public/code-review/issues.json": {
                        "docs/folderA/index.rst": [
                            {
                                "path": "docs/folderA/index.rst",
                                "line": 1,
                                "column": 1,
                                "level": "warning",
                                "check": "some-check",
                                "message": "A doc issue",
                            }
                        ]
                    },
                    "public/firefox-source-docs-url.txt": "http://firefox-test-docs.mozilla.org/index.html",
                    "public/trees.json": {"section1": "docs/folderA"},
                },
            },
        }
    )
    # Bypass revision publication check (backend storage is disabled in tests)
    mock_workflow.backend_api.publish_revision = lambda rev: {}

    issues, task_failures, notices, reviewers = mock_workflow.find_issues(
        mock_revision, "remoteTryTask"
    )

    assert len(issues) == 1
    assert issues[0].message == "A doc issue"
    assert task_failures == []
    assert len(notices) == 1
    assert "docs/folderA/index.rst" in notices[0]


def test_find_issues_doc_upload_failure_reported_once(mock_workflow, mock_revision):
    """
    A failed source-test-doc-upload task with no parsed issues or patches
    must only be reported once as a task failure, even though DocUploadTask
    exercises both the AnalysisTask and NoticeTask dispatch branches.
    """
    mock_revision.files = []

    mock_workflow.setup_mock_tasks(
        {
            "remoteTryTask": {
                "dependencies": ["doc-upload-task"],
                "name": "code-review-issues",
            },
            "doc-upload-task": {
                "name": "source-test-doc-upload",
                "state": "failed",
                "artifacts": {},
            },
        }
    )
    mock_workflow.backend_api.publish_revision = lambda rev: {}

    issues, task_failures, notices, reviewers = mock_workflow.find_issues(
        mock_revision, "remoteTryTask"
    )

    assert issues == []
    assert notices == []
    assert len(task_failures) == 1


def test_find_build_test_issues(mock_workflow, mock_revision):
    mock_workflow.setup_mock_tasks(
        {
            "failed-build": {
                "name": "build-linux64/opt",
                "state": "failed",
                "artifacts": {
                    "public/logs/live_backing.log": "\n".join(
                        [
                            "[taskcluster 2026-10-14T13:02:11.310Z] Worker Type settings:",
                            "[task 2026-10-14T13:10:45.004Z] 13:10:45     INFO -  foo.cpp:18:1: error: broken",
                            "[task 2026-10-14T13:10:46.004Z] 13:10:46     INFO -  compiling bar.cpp",
                        ]
                    )
                },
            },
            "passed-build": {"name": "build-win64/debug", "state": "completed"},
            "docker-image": {
                "name": "build-docker-image-debian12-base",
                "state": "failed",
            },
            "lint": {"name": "source-test-unsupported", "state": "failed"},
        }
    )

    issues, _, notices, reviewers = mock_workflow.find_build_test_issues(
        mock_revision, "remoteTryGroup"
    )

    assert len(issues) == 1
    assert isinstance(issues[0], BuildIssue)
    assert issues[0].task_id == "failed-build"
    assert issues[0].revision is mock_revision
    assert issues[0].error_lines == ["foo.cpp:18:1: error: broken"]
    assert notices == []
    assert reviewers == []


def test_find_build_test_issues_task_error(mock_workflow, mock_revision):
    mock_workflow.setup_mock_tasks(
        {
            "failed-build": {"name": "build-linux64/opt", "state": "failed"},
            "mozlint": {"name": "source-test-mozlint-eslint", "state": "failed"},
        }
    )

    with mock.patch.object(
        MozLintTask, "parse_issues", side_effect=Exception("broken artifact")
    ):
        with pytest.raises(Exception, match="broken artifact"):
            mock_workflow.find_build_test_issues(mock_revision, "remoteTryGroup")


def test_find_build_test_issues_exception(mock_workflow, mock_revision):
    mock_workflow.setup_mock_tasks(
        {
            "exception-build": {"name": "build-linux64/opt", "state": "exception"},
            "canceled-build": {"name": "build-win64/debug", "state": "exception"},
        }
    )
    mock_workflow.queue_service._status["canceled-build"]["status"]["runs"][0][
        "reasonResolved"
    ] = "canceled"

    issues, task_failures, _, _ = mock_workflow.find_build_test_issues(
        mock_revision, "remoteTryGroup"
    )

    assert issues == []
    assert [task.id for task in task_failures] == ["exception-build"]


def test_find_build_test_issues_all_pages(mock_workflow, mock_revision):
    mock_workflow.setup_mock_tasks(
        {
            f"failed-build-{i}": {"name": f"build-linux64-{i}/opt", "state": "failed"}
            for i in range(3)
        }
    )

    with mock.patch.object(
        mock_workflow.queue_service,
        "listTaskGroup",
        wraps=mock_workflow.queue_service.listTaskGroup,
    ) as list_task_group:
        issues, _, _, _ = mock_workflow.find_build_test_issues(
            mock_revision, "remoteTryGroup"
        )

    assert "paginationHandler" in list_task_group.call_args.kwargs
    assert sorted(issue.task_id for issue in issues) == [
        "failed-build-0",
        "failed-build-1",
        "failed-build-2",
    ]


def test_run_build_test(mock_workflow, mock_revision):
    issues = [mock.Mock()]
    mock_workflow.index = mock.Mock()
    mock_workflow.publish = mock.Mock()
    mock_workflow.find_build_test_issues = mock.Mock(return_value=(issues, [], [], []))

    assert mock_workflow.run(mock_revision, AnalysisMode.BuildTest) == issues

    mock_workflow.find_build_test_issues.assert_called_once_with(
        mock_revision, "remoteTryGroup"
    )
    assert mock_workflow.index.call_args_list == [
        mock.call(mock_revision, namespace_suffixes=["build-test"], state="started")
    ]
    assert mock_revision._state == BuildState.Work
    mock_workflow.publish.assert_called_once_with(
        mock_revision,
        issues,
        [],
        [],
        [],
        AnalysisMode.BuildTest,
        ["build-test"],
        publish_to_backend=False,
    )


@pytest.mark.parametrize(
    "tasks, expected_state",
    [
        ({"passed-build": {"name": "build-linux64/opt"}}, BuildState.Pass),
        (
            {
                "passed-build": {"name": "build-linux64/opt"},
                "failed-build": {"name": "build-win64/debug", "state": "failed"},
            },
            BuildState.Fail,
        ),
    ],
)
def test_run_build_test_state(mock_workflow, mock_revision, tasks, expected_state):
    mock_workflow.setup_mock_tasks(tasks)

    mock_workflow.run(mock_revision, AnalysisMode.BuildTest)

    assert mock_revision._state == expected_state


@pytest.mark.parametrize(
    "analysis_mode, expected",
    [(AnalysisMode.Lint, "lint"), (AnalysisMode.BuildTest, "build")],
)
def test_publish_filters_issues_by_analysis_mode(
    mock_workflow, mock_revision, mock_task, analysis_mode, expected
):
    issues = {
        "build": BuildIssue(
            task_id="failed-build",
            analyzer=mock_task(BuildTask, "build-linux64/opt"),
            revision=mock_revision,
            level=Level.Error,
            message="build failed",
        ),
        "lint": MozLintIssue(
            mock_task(MozLintTask, "source-test-mozlint-eslint"),
            "dom/file.js",
            column=1,
            level="error",
            lineno=42,
            linter="eslint",
            message="Some issue",
            check="no-shadow",
            revision=mock_revision,
        ),
    }
    reporter = mock.Mock()
    mock_workflow.reporters = {"mock": reporter}
    mock_workflow.backend_api.publish_issues = mock.Mock()

    mock_workflow.publish(
        mock_revision, list(issues.values()), [], [], [], analysis_mode, [""]
    )

    reporter.publish.assert_called_once_with(
        [issues[expected]], mock_revision, [], [], [], analysis_mode
    )


@pytest.mark.parametrize("publish_to_backend", [True, False])
def test_publish_to_backend(
    mock_workflow, mock_revision, mock_task, publish_to_backend
):
    issue = BuildIssue(
        task_id="failed-build",
        analyzer=mock_task(BuildTask, "build-linux64/opt"),
        revision=mock_revision,
        level=Level.Error,
        message="build failed",
    )
    mock_workflow.backend_api.publish_issues = mock.Mock()

    mock_workflow.publish(
        mock_revision,
        [issue],
        [],
        [],
        [],
        AnalysisMode.BuildTest,
        ["build-test"],
        publish_to_backend=publish_to_backend,
    )

    if publish_to_backend:
        mock_workflow.backend_api.publish_issues.assert_called_once_with(
            [issue], mock_revision
        )
    else:
        mock_workflow.backend_api.publish_issues.assert_not_called()
    assert mock_revision._state == BuildState.Fail


def test_on_production(mock_config, mock_repositories):
    """
    Test the production environment detection
    """
    # By default mock_config is not as production
    assert mock_config.app_channel == "test"
    assert mock_config.taskcluster.local is True
    assert mock_config.on_production is False
    assert mock_config.taskcluster_url is None

    # Taskcluster env + testing is not production
    os.environ["TASK_ID"] = "testingTask"
    os.environ["RUN_ID"] = "0"
    testing = Settings()
    testing.setup("testing", [], mock_repositories)
    assert testing.app_channel == "testing"
    assert testing.taskcluster.local is False
    assert testing.on_production is False
    assert (
        testing.taskcluster_url
        == "https://firefox-ci-tc.services.mozilla.com/tasks/testingTask"
    )

    # Taskcluster env + production is production
    os.environ["TASK_ID"] = "prodTask"
    os.environ["RUN_ID"] = "0"
    testing = Settings()
    testing.setup("production", [], mock_repositories)
    assert testing.app_channel == "production"
    assert testing.taskcluster.local is False
    assert testing.on_production is True
    assert (
        testing.taskcluster_url
        == "https://firefox-ci-tc.services.mozilla.com/tasks/prodTask"
    )


def test_mercurial_cache_checkout(mock_config, tmpdir):
    """
    Test the checkout used to build issues is shared with the analysis task
    for configured repositories
    """
    mock_config.mercurial_cache = None
    assert (
        mock_config.mercurial_cache_checkout("https://hg.mozilla.org/mozilla-central")
        is None
    )

    mock_config.mercurial_cache = tmpdir
    # Same directory as the one used by the analysis task (named after the repository)
    assert (
        mock_config.mercurial_cache_checkout("https://hg.mozilla.org/mozilla-central")
        == tmpdir / "mozilla-central"
    )
    assert (
        mock_config.mercurial_cache_checkout("https://hg.mozilla.org/mozilla-central/")
        == tmpdir / "mozilla-central"
    )

    # Fallback for unknown repositories, logged only once per URL
    mock_config.mercurial_cache_fallback_logged.clear()
    with capture_logs() as cap_logs:
        for _ in range(2):
            assert (
                mock_config.mercurial_cache_checkout("https://hg.mozilla.org/unknown")
                == tmpdir / "checkout"
            )
            assert mock_config.mercurial_cache_checkout(None) == tmpdir / "checkout"
    assert [log["url"] for log in cap_logs] == ["https://hg.mozilla.org/unknown", None]


def test_before_after(mock_taskcluster_config, mock_workflow, mock_task, mock_revision):
    """
    Test the before/after feature running a try task workflow.
    Issues that are unknown to the backend are tagged as new issues.
    """
    mock_taskcluster_config.secrets = {"BEFORE_AFTER_RATIO": 1}
    issues = [
        ClangFormatIssue(
            mock_task(ClangFormatTask, "source-test-clang-format"),
            "outside/of/the/patch.cpp",
            [(42, 42, b"This is a new warning.")],
            mock_revision,
        ),
        ClangFormatIssue(
            mock_task(ClangFormatTask, "source-test-clang-format"),
            "outside/of/the/patch.cpp",
            [(42, 42, b"This is a warning known by the backend.")],
            mock_revision,
        ),
    ]
    mock_workflow.publish = mock.Mock()
    mock_workflow.find_issues = mock.Mock()
    mock_workflow.find_issues.return_value = (
        issues,
        # No failure nor notices nor reviewers
        [],
        [],
        [],
    )
    mock_workflow.queue_service.task = lambda x: {}
    mock_workflow.mercurial_repository = None
    mock_workflow.backend_api.url = "https://backend.test"
    mock_workflow.backend_api.username = "root"
    mock_workflow.backend_api.password = "hunter2"
    for index, hash_val in enumerate(("aaaa", "bbbb")):
        issues[index].hash = hash_val

    current_date = datetime.now().strftime("%Y-%m-%d")
    responses.add(
        responses.GET,
        f"https://backend.test/v1/issues/mozilla-central/?path=outside%2Fof%2Fthe%2Fpatch.cpp&date={current_date}",
        json={
            "count": 2,
            "previous": None,
            "next": None,
            "results": [
                {"id": "issue 1", "hash": "bbbb"},
                {"id": "issue 42", "hash": "xxxx"},
            ],
        },
    )

    # Set backend ID as the publication is disabled for tests
    mock_revision.id = 1337
    assert mock_revision.before_after_feature is True
    mock_workflow.run(mock_revision, AnalysisMode.Lint)
    assert mock_workflow.publish.call_args_list == [
        mock.call(
            mock_revision,
            issues,
            [],
            [],
            [],
            AnalysisMode.Lint,
            ["", "lint"],
        )
    ]
    assert issues[0].new_issue is True
    assert issues[1].new_issue is False


def test_publish_link_duplicate_harbormaster_uri(mock_workflow):
    """
    When publish_link raises a ConduitError due to a duplicate Harbormaster URI
    artifact (e.g. on task retry after worker shutdown), the error should be
    swallowed and a warning logged.
    """
    mock_workflow.update_build = True
    mock_workflow.phabricator = mock.MagicMock()
    mock_workflow.phabricator.create_harbormaster_uri.side_effect = ConduitError(
        "Duplicate entry",
        error_code="ERR-CONDUIT-CORE",
        error_info="Duplicate entry 'uri-VEVIsJOfD0wc' for key 'harbormaster_buildartifact.key_artifact'",
    )

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.build_target_phid = "PHID-HMBT-test"

    mock_workflow.publish_link(
        revision, "treeherder", "CI Jobs", "https://treeherder.mozilla.org/"
    )

    mock_workflow.phabricator.create_harbormaster_uri.assert_called_once()


def test_publish_link_reraises_other_conduit_errors(mock_workflow):
    """
    Non-duplicate ConduitErrors must still propagate from publish_link.
    """
    mock_workflow.update_build = True
    mock_workflow.phabricator = mock.MagicMock()
    mock_workflow.phabricator.create_harbormaster_uri.side_effect = ConduitError(
        "Some other error",
        error_code="ERR-CONDUIT-CORE",
        error_info="Some unrelated error",
    )

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.build_target_phid = "PHID-HMBT-test"

    with pytest.raises(ConduitError):
        mock_workflow.publish_link(
            revision, "treeherder", "CI Jobs", "https://treeherder.mozilla.org/"
        )


def test_publish_link(mock_phabricator, mock_workflow):
    # Allow build updates
    mock_workflow.update_build = True

    with mock_phabricator as api:
        mock_workflow.phabricator = api

        revision = PhabricatorRevision.from_phabricator_trigger(
            build_target_phid="PHID-HMBT-test",
            phabricator=api,
        )
        mock_workflow.publish_link(
            revision,
            "some-unique-code",
            "A nice display name",
            "http://taskcluster/x.y.z",
        )

    # Check request & response for the link publication
    call = responses.calls[-1]
    assert call.request.method == "POST"
    assert call.request.url == "http://phabricator.test/api/harbormaster.createartifact"
    assert (
        unquote_plus(call.request.body)
        == 'params={"buildTargetPHID": "PHID-HMBT-test", "artifactType": "uri", "artifactKey": "some-unique-code", "artifactData": {"uri": "http://taskcluster/x.y.z", "name": "A nice display name", "ui.external": true}, "__conduit__": {"token": "deadbeef"}}&output=json'
    )


TREEHERDER_LOG = """
2026-08-21 05:51:27 [INFO] Mercurial stdout=b'remote: Follow the progress of your build on Treeherder:\\n'
2026-08-21 05:51:27 [INFO] Mercurial stdout=b'remote:   https://treeherder.mozilla.org/jobs?repo=try&revision=02af25daadb64b42939b5a3f382c6d5f2a6f311e\\n'
2026-08-21 05:51:41 [INFO] Created HarborMaster link on PHID-HMBT-old : https://treeherder.mozilla.org/#/jobs?repo=try&revision=02af25daadb64b42939b5a3f382c6d5f2a6f311e
"""

DECISION_ROUTE = (
    "gecko.v2.try.revision.02af25daadb64b42939b5a3f382c6d5f2a6f311e.taskgraph.decision"
)

BUILDABLES = {
    "PHID-HMBB-old": "PHID-DIFF-old",
    "PHID-HMBB-current": "PHID-DIFF-current",
}

DIFF_IDS = {
    "PHID-DIFF-old": 1,
    "PHID-DIFF-current": 2,
    "PHID-DIFF-next": 3,
}

CURRENT_DIFF_ID = DIFF_IDS["PHID-DIFF-current"]


def mock_harbormaster(logs, buildables=BUILDABLES, abort_error=None, diff_ids=DIFF_IDS):
    """
    Mock the Conduit calls used to cancel and abort the previous updates

    logs maps a file PHID to a (build target PHID, raw log content) tuple.
    buildables maps a buildable PHID to the PHID of the diff it builds.
    diff_ids maps a diff PHID to its id, which orders the updates.
    abort_error is raised on every harbormaster.sendmessage call when set.

    Every buildable has a single build, itself having a single build target,
    all sharing the suffix of the buildable PHID. (In production these suffixs
    differ; but for testing purposes this is fine.)
    """
    api = mock.MagicMock()

    def related(phids, kind):
        return {
            "data": [
                {"phid": f"PHID-{kind}-{phid.rsplit('-', 1)[1]}"} for phid in phids
            ]
        }

    def request(path, **payload):
        if path == "harbormaster.buildable.search":
            return {
                "data": [
                    {"phid": phid, "fields": {"objectPHID": diff_phid}}
                    for phid, diff_phid in sorted(buildables.items())
                ]
            }

        if path == "differential.diff.search":
            return {
                "data": [
                    {"phid": phid, "id": diff_ids[phid]}
                    for phid in payload["constraints"]["phids"]
                    if phid in diff_ids
                ]
            }

        if path == "harbormaster.build.search":
            return related(payload["constraints"]["buildables"], "HMBD")

        if path == "harbormaster.target.search":
            return related(payload["constraints"]["buildPHIDs"], "HMBT")

        if path == "harbormaster.sendmessage":
            if abort_error is not None:
                raise abort_error
            return None

        if path == "harbormaster.log.search":
            wanted = payload["constraints"]["buildTargetPHIDs"]
            return {
                "data": [
                    {"fields": {"filePHID": phid}}
                    for phid, (target, _) in sorted(logs.items())
                    if target in wanted
                ]
            }

        if path == "file.download":
            content = logs[payload["phid"]][1]
            return base64.b64encode(content.encode("utf-8")).decode("utf-8")

        raise AssertionError(f"Unexpected conduit call {path}")

    api.request.side_effect = request
    return api


def test_find_try_decision_task(mock_config, mock_workflow):
    """
    The try changeset is read from the publication task log, then resolved to a
    decision task through the Taskcluster index
    """
    mock_workflow.queue_service.session.add(
        "get",
        "http://tc.test/oldPublicationTask/artifacts/public/logs/live_backing.log",
        TREEHERDER_LOG,
    )
    mock_workflow.index_service.configure(
        {"decisionTask": {"route": DECISION_ROUTE}},
    )

    assert mock_workflow.find_try_decision_task("oldPublicationTask") == "decisionTask"


def test_find_try_decision_task_without_try_push(mock_config, mock_workflow):
    """
    A build that never reached the try push stage is simply skipped
    """
    mock_workflow.queue_service.session.add(
        "get",
        "http://tc.test/oldPublicationTask/artifacts/public/logs/live_backing.log",
        "Nothing was pushed to try",
    )
    mock_workflow.index_service.configure({})

    assert mock_workflow.find_try_decision_task("oldPublicationTask") is None


def test_find_try_decision_task_missing_log(mock_config, mock_workflow):
    """
    An expired or missing publication log does not raise
    """
    mock_workflow.index_service.configure({})

    assert mock_workflow.find_try_decision_task("oldPublicationTask") is None


def abort_calls(phabricator):
    return [
        call.kwargs
        for call in phabricator.request.call_args_list
        if call.args[0] == "harbormaster.sendmessage"
    ]


def test_cancel_previous(mock_config, mock_workflow):
    """
    Task groups of previous try pushes are cancelled, and the buildables of the
    previous updates are aborted
    """
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "currentTask", 0, False)
    mock_workflow.phabricator = mock_harbormaster(
        {
            "PHID-FILE-old-headers": ("PHID-HMBT-old", "HTTP 200\n"),
            "PHID-FILE-old-body": ("PHID-HMBT-old", '{"taskId": "oldPublicationTask"}'),
            "PHID-FILE-current-body": (
                "PHID-HMBT-current",
                '{"taskId": "currentTask"}',
            ),
        }
    )
    mock_workflow.queue_service.session.add(
        "get",
        "http://tc.test/oldPublicationTask/artifacts/public/logs/live_backing.log",
        TREEHERDER_LOG,
    )
    mock_workflow.index_service.configure({"decisionTask": {"route": DECISION_ROUTE}})

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.phabricator_phid = "PHID-DREV-1"
    revision.diff_phid = "PHID-DIFF-current"
    revision.diff_id = CURRENT_DIFF_ID
    revision.build_target_phid = "PHID-HMBT-current"

    mock_workflow.cancel_previous(revision)

    assert mock_workflow.queue_service.sealed_groups == ["decisionTask"]
    assert mock_workflow.queue_service.cancelled_groups == ["decisionTask"]
    assert abort_calls(mock_workflow.phabricator) == [
        {"receiver": "PHID-HMBB-old", "type": "abort"}
    ]


def test_cancel_previous_without_previous_build(mock_config, mock_workflow):
    """
    A revision whose only buildable is the current one has nothing to cancel
    nor to abort, and no Conduit call is made past the buildable lookup
    """
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "currentTask", 0, False)
    mock_workflow.phabricator = mock_harbormaster(
        {
            "PHID-FILE-current-body": (
                "PHID-HMBT-current",
                '{"taskId": "currentTask"}',
            ),
        },
        buildables={"PHID-HMBB-current": "PHID-DIFF-current"},
    )
    mock_workflow.index_service.configure({})

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.phabricator_phid = "PHID-DREV-1"
    revision.diff_phid = "PHID-DIFF-current"
    revision.diff_id = CURRENT_DIFF_ID
    revision.build_target_phid = "PHID-HMBT-current"

    mock_workflow.cancel_previous(revision)

    assert mock_workflow.queue_service.cancelled_groups == []
    assert abort_calls(mock_workflow.phabricator) == []
    mock_workflow.phabricator.request.assert_called_once()


def test_cancel_previous_without_publication_task(mock_config, mock_workflow):
    """
    A previous buildable whose logs hold no publication task is still aborted
    """
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "currentTask", 0, False)
    mock_workflow.phabricator = mock_harbormaster(
        {"PHID-FILE-old-headers": ("PHID-HMBT-old", "HTTP 200\n")}
    )
    mock_workflow.index_service.configure({})

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.phabricator_phid = "PHID-DREV-1"
    revision.diff_phid = "PHID-DIFF-current"
    revision.diff_id = CURRENT_DIFF_ID
    revision.build_target_phid = "PHID-HMBT-current"

    mock_workflow.cancel_previous(revision)

    assert mock_workflow.queue_service.cancelled_groups == []
    assert abort_calls(mock_workflow.phabricator) == [
        {"receiver": "PHID-HMBB-old", "type": "abort"}
    ]


def test_cancel_previous_abort_failure(mock_config, mock_workflow):
    """
    A Conduit failure while aborting a buildable does not break the workflow
    """
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "currentTask", 0, False)
    mock_workflow.phabricator = mock_harbormaster(
        {
            "PHID-FILE-old-body": ("PHID-HMBT-old", '{"taskId": "oldPublicationTask"}'),
        },
        abort_error=ConduitError("Boom"),
    )
    mock_workflow.queue_service.session.add(
        "get",
        "http://tc.test/oldPublicationTask/artifacts/public/logs/live_backing.log",
        TREEHERDER_LOG,
    )
    mock_workflow.index_service.configure({"decisionTask": {"route": DECISION_ROUTE}})

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.phabricator_phid = "PHID-DREV-1"
    revision.diff_phid = "PHID-DIFF-current"
    revision.diff_id = CURRENT_DIFF_ID
    revision.build_target_phid = "PHID-HMBT-current"

    mock_workflow.cancel_previous(revision)

    assert mock_workflow.queue_service.cancelled_groups == ["decisionTask"]
    assert abort_calls(mock_workflow.phabricator) == [
        {"receiver": "PHID-HMBB-old", "type": "abort"}
    ]


def test_cancel_previous_publication_tasks_failure(mock_config, mock_workflow):
    """
    A Conduit failure while looking for publication tasks does not prevent the
    previous buildables from being aborted
    """
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "currentTask", 0, False)
    mock_workflow.phabricator = mock_harbormaster({})
    harbormaster = mock_workflow.phabricator.request.side_effect

    def request(path, **payload):
        if path == "harbormaster.build.search":
            raise ConduitError("Boom")
        return harbormaster(path, **payload)

    mock_workflow.phabricator.request.side_effect = request

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.phabricator_phid = "PHID-DREV-1"
    revision.diff_phid = "PHID-DIFF-current"
    revision.diff_id = CURRENT_DIFF_ID
    revision.build_target_phid = "PHID-HMBT-current"

    mock_workflow.cancel_previous(revision)

    assert mock_workflow.queue_service.cancelled_groups == []
    assert abort_calls(mock_workflow.phabricator) == [
        {"receiver": "PHID-HMBB-old", "type": "abort"}
    ]


def test_cancel_previous_conduit_failure(mock_config, mock_workflow):
    """
    A Conduit failure while listing previous buildables is swallowed
    """
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "currentTask", 0, False)
    mock_workflow.phabricator = mock.MagicMock()
    mock_workflow.phabricator.request.side_effect = ConduitError("Boom")

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.phabricator_phid = "PHID-DREV-1"
    revision.diff_phid = "PHID-DIFF-current"
    revision.diff_id = CURRENT_DIFF_ID
    revision.build_target_phid = "PHID-HMBT-current"

    mock_workflow.cancel_previous(revision)

    assert mock_workflow.queue_service.cancelled_groups == []
    mock_workflow.phabricator.request.assert_called_once()


def test_cancel_previous_ignores_later_buildables(mock_config, mock_workflow):
    """
    The buildable of a later diff is left alone: it belongs to an update that is
    itself superseding the one being processed
    """
    mock_config.taskcluster = TaskCluster("/tmp/dummy", "currentTask", 0, False)
    mock_workflow.phabricator = mock_harbormaster(
        {
            "PHID-FILE-old-body": ("PHID-HMBT-old", '{"taskId": "oldPublicationTask"}'),
            "PHID-FILE-next-body": (
                "PHID-HMBT-next",
                '{"taskId": "nextPublicationTask"}',
            ),
        },
        buildables={
            "PHID-HMBB-old": "PHID-DIFF-old",
            "PHID-HMBB-current": "PHID-DIFF-current",
            "PHID-HMBB-next": "PHID-DIFF-next",
        },
    )
    mock_workflow.queue_service.task_states["oldPublicationTask"] = "running"
    mock_workflow.queue_service.task_states["nextPublicationTask"] = "running"
    mock_workflow.index_service.configure({})

    revision = mock.MagicMock(spec=PhabricatorRevision)
    revision.phabricator_phid = "PHID-DREV-1"
    revision.diff_phid = "PHID-DIFF-current"
    revision.diff_id = CURRENT_DIFF_ID
    revision.build_target_phid = "PHID-HMBT-current"

    mock_workflow.cancel_previous(revision)

    assert mock_workflow.queue_service.cancelled_tasks == ["oldPublicationTask"]
    assert abort_calls(mock_workflow.phabricator) == [
        {"receiver": "PHID-HMBB-old", "type": "abort"}
    ]


@pytest.mark.parametrize("before_after_ratio", [0, 1])
@pytest.mark.parametrize("has_issues", [False, True])
def test_clone_repository_skipped_without_issues(
    mock_taskcluster_config,
    mock_workflow,
    mock_task,
    mock_revision,
    before_after_ratio,
    has_issues,
):
    """
    The local clone is only needed to build the issues hashes,
    so it is skipped when there are no issues
    """
    mock_taskcluster_config.secrets = {"BEFORE_AFTER_RATIO": before_after_ratio}
    issues = (
        [
            ClangFormatIssue(
                mock_task(ClangFormatTask, "source-test-clang-format"),
                "dom/file.cpp",
                [(42, 42, b"This is a new warning.")],
                mock_revision,
            )
        ]
        if has_issues
        else []
    )
    mock_workflow.publish = mock.Mock()
    mock_workflow.find_issues = mock.Mock(return_value=(issues, [], [], []))
    mock_workflow.find_previous_issues = mock.Mock()
    mock_workflow.clone_repository = mock.Mock()
    mock_workflow.queue_service.task = lambda x: {}
    # Set backend ID as it is required by the before/after feature
    mock_revision.id = 1337
    assert mock_revision.before_after_feature is bool(before_after_ratio)

    mock_workflow.run(mock_revision, AnalysisMode.Lint)

    if has_issues:
        mock_workflow.clone_repository.assert_called_once_with(mock_revision, issues)
    else:
        mock_workflow.clone_repository.assert_not_called()
    assert mock_workflow.find_previous_issues.called is bool(before_after_ratio)


def test_clone_repository_extracts_issues_files(
    mock_config, mock_workflow, mock_task, mock_revision, tmp_path, monkeypatch
):
    """
    Only the files with issues are extracted from the local repository,
    outside of the persisted cache
    """
    mock_config.mercurial_cache = tmp_path
    files_dir = mock_config.mercurial_cache_files
    assert tmp_path not in files_dir.parents

    checkouts = []
    monkeypatch.setattr(
        "code_review_bot.workflow.robust_checkout",
        lambda **kwargs: checkouts.append(kwargs),
    )

    def _cat_files(repo_dir, revision, paths, output_dir):
        for path in paths:
            (output_dir / path).parent.mkdir(parents=True, exist_ok=True)
            (output_dir / path).write_text("\n" * 41 + "content\n")

    cat_files = mock.Mock(side_effect=_cat_files)
    monkeypatch.setattr("code_review_bot.workflow.cat_files", cat_files)

    issue = MozLintIssue(
        mock_task(MozLintTask, "source-test-mozlint-eslint"),
        "dom/file.js",
        column=1,
        level="warning",
        lineno=42,
        linter="eslint",
        message="Some issue",
        check="no-shadow",
        revision=mock_revision,
    )

    try:
        mock_workflow.clone_available = False
        mock_workflow.clone_repository(mock_revision, [issue, issue])

        assert checkouts == [
            {
                "repo_upstream_url": mock_revision.base_repository,
                "repo_url": mock_revision.head_repository,
                "revision": mock_revision.head_changeset,
                "checkout_dir": tmp_path / "mozilla-central",
                "sharebase_dir": tmp_path / "shared",
                "noupdate": True,
            }
        ]
        cat_files.assert_called_once_with(
            repo_dir=tmp_path / "mozilla-central",
            revision=mock_revision.head_changeset,
            paths=["dom/file.js"],
            output_dir=files_dir,
        )

        # The hash is built from the extracted file
        assert issue.hash is not None
        assert issue.file_exists is True
    finally:
        mock_config.mercurial_cache = None


LINT_ROUTES = ["project.relman.codereview.v1.try_ending"]
TASK_GROUP_ROUTES = ["index.project.relman.codereview.v1.task_groups.abcdef"]
BUILD_TEST_ROUTES = ["project.relman.codereview-build-test.v1.try_ending"]
CANCELED = {"reasonResolved": "canceled"}


def build_test_group(code_review_state="unscheduled"):
    return {
        "task-group": {"name": "code-review-watch", "routes": TASK_GROUP_ROUTES},
        "code-review": {
            "name": "code-review-build-test-issues",
            "state": code_review_state,
            "dependencies": ["build", "other-build"],
            "requires": "all-resolved",
            "routes": BUILD_TEST_ROUTES,
        },
        "toolchain": {
            "name": "toolchain-linux64-clang",
            "state": "failed",
        },
        "build": {
            "name": "build-linux64/opt",
            "state": "unscheduled",
            "dependencies": ["toolchain"],
        },
        "other-build": {"name": "build-win64/opt", "state": "running"},
    }


def test_reap_blocked_tasks(mock_workflow):
    mock_workflow.setup_mock_tasks(build_test_group())
    mock_workflow.index_service.task_groups = ["task-group"]

    assert mock_workflow.reap_blocked_tasks() == ["build"]
    assert mock_workflow.queue_service.cancelled_tasks == ["build"]


def test_reap_blocked_tasks_lists_task_groups_namespace(mock_workflow):
    mock_workflow.setup_mock_tasks(build_test_group())
    mock_workflow.index_service.task_groups = ["task-group"]

    with mock.patch.object(
        mock_workflow.index_service,
        "listTasks",
        wraps=mock_workflow.index_service.listTasks,
    ) as list_tasks:
        mock_workflow.reap_blocked_tasks()

    assert list_tasks.call_args.args == ("project.relman.codereview.v1.task_groups",)
    assert "paginationHandler" in list_tasks.call_args.kwargs


@pytest.mark.parametrize("state", ["completed", "exception", "pending"])
def test_reap_blocked_tasks_skips_resolved_code_review(mock_workflow, state):
    mock_workflow.setup_mock_tasks(build_test_group(code_review_state=state))
    mock_workflow.index_service.task_groups = ["task-group"]

    assert mock_workflow.reap_blocked_tasks() == []
    assert mock_workflow.queue_service.cancelled_tasks == []


def test_reap_blocked_tasks_unknown_task_group(mock_workflow):
    mock_workflow.setup_mock_tasks(build_test_group())
    mock_workflow.index_service.task_groups = ["missing", "task-group"]

    assert mock_workflow.reap_blocked_tasks() == ["build"]


def test_reap_blocked_tasks_any_code_review_unscheduled(mock_workflow):
    tasks = build_test_group()
    tasks["lint-code-review"] = {
        "name": "code-review-issues",
        "state": "completed",
        "requires": "all-resolved",
        "routes": LINT_ROUTES,
    }
    mock_workflow.setup_mock_tasks(tasks)
    mock_workflow.index_service.task_groups = ["task-group"]

    assert mock_workflow.reap_blocked_tasks() == ["build"]


def test_reap_blocked_tasks_without_code_review(mock_workflow):
    tasks = build_test_group()
    del tasks["code-review"]
    mock_workflow.setup_mock_tasks(tasks)
    mock_workflow.index_service.task_groups = ["task-group"]

    assert mock_workflow.reap_blocked_tasks() == []


def test_reap_blocked_tasks_external_dependency(mock_workflow):
    tasks = build_test_group()
    del tasks["toolchain"]
    mock_workflow.setup_mock_tasks(tasks)
    mock_workflow.queue_service._status["toolchain"] = {
        "status": {
            "taskId": "toolchain",
            "taskGroupId": "otherGroup",
            "state": "exception",
            "runs": [
                {
                    "runId": 0,
                    "reasonResolved": "worker-shutdown",
                }
            ],
        }
    }
    mock_workflow.index_service.task_groups = ["task-group"]

    assert mock_workflow.reap_blocked_tasks() == ["build"]


def test_reap_blocked_tasks_only_loads_external_dependencies_of_unscheduled(
    mock_workflow,
):
    tasks = build_test_group()
    del tasks["toolchain"]
    tasks["lint"] = {
        "name": "source-test-mozlint-eslint",
        "dependencies": ["docker-image"],
    }
    mock_workflow.setup_mock_tasks(tasks)
    queue = mock_workflow.queue_service
    queue._status["toolchain"] = {
        "status": {"taskId": "toolchain", "state": "failed", "runs": [{"runId": 0}]}
    }
    mock_workflow.index_service.task_groups = ["task-group"]

    with mock.patch.object(queue, "status", wraps=queue.status) as status:
        assert mock_workflow.reap_blocked_tasks() == ["build"]

    assert [
        call.args[0] for call in status.call_args_list if call.args[0] not in tasks
    ] == ["toolchain"]


def test_reap_blocked_tasks_cancel_failure(mock_workflow):
    tasks = build_test_group()
    tasks["test"] = {
        "name": "test-linux64/opt-mochitest",
        "state": "unscheduled",
        "dependencies": ["build"],
    }
    tasks["code-review"]["dependencies"].append("test")
    mock_workflow.setup_mock_tasks(tasks)
    mock_workflow.index_service.task_groups = ["task-group"]

    cancel_task = mock_workflow.queue_service.cancelTask

    def _cancel(task_id):
        if task_id == "build":
            raise Exception("Nope")
        return cancel_task(task_id)

    mock_workflow.queue_service.cancelTask = _cancel

    assert mock_workflow.reap_blocked_tasks() == ["test"]


def test_reap_mode(mock_repositories, monkeypatch):
    monkeypatch.setenv("CODE_REVIEW_REAP", "1")
    reap = Settings()
    reap.setup("test", [], mock_repositories)

    assert reap.reap is True
    assert reap.try_group_id is None
    assert reap.analysis_mode is None


def test_reap_blocked_tasks_canceled_dependency(mock_workflow):
    tasks = build_test_group()
    tasks["toolchain"]["state"] = "exception"
    tasks["toolchain"]["run"] = CANCELED
    mock_workflow.setup_mock_tasks(tasks)
    mock_workflow.index_service.task_groups = ["task-group"]

    assert mock_workflow.reap_blocked_tasks() == ["build"]


def two_blocked_groups(mock_workflow, list_task_group):
    groups = {}
    for group_id in ("group-a", "group-b"):
        groups[group_id] = {
            f"{group_id}-{task_id}": {
                **desc,
                "group": group_id,
                "dependencies": [
                    f"{group_id}-{dep}" for dep in desc.get("dependencies", [])
                ],
            }
            for task_id, desc in build_test_group().items()
        }
    mock_workflow.setup_mock_tasks({**groups["group-a"], **groups["group-b"]})
    mock_workflow.index_service.task_groups = [
        "group-a-task-group",
        "group-b-task-group",
    ]

    queue = mock_workflow.queue_service

    def _list_task_group(group_id, paginationHandler):
        list_task_group(group_id)
        paginationHandler(
            {
                "tasks": [
                    {
                        "task": queue.task(task_id),
                        "status": queue.status(task_id)["status"],
                    }
                    for task_id in groups[group_id]
                ]
            }
        )

    queue.listTaskGroup = _list_task_group


def test_reap_blocked_tasks_shared_external_dependency(mock_workflow):
    two_blocked_groups(mock_workflow, lambda group_id: None)
    queue = mock_workflow.queue_service
    for group_id in ("group-a", "group-b"):
        queue._tasks[f"{group_id}-build"]["dependencies"] = ["toolchain"]
    queue._status["toolchain"] = {
        "status": {"taskId": "toolchain", "state": "failed", "runs": [{"runId": 0}]}
    }

    with mock.patch.object(queue, "status", wraps=queue.status) as status:
        assert mock_workflow.reap_blocked_tasks() == ["group-a-build", "group-b-build"]

    assert [call.args[0] for call in status.call_args_list].count("toolchain") == 2


def test_reap_blocked_tasks_multiple_groups(mock_workflow):
    two_blocked_groups(mock_workflow, lambda group_id: None)

    assert mock_workflow.reap_blocked_tasks() == ["group-a-build", "group-b-build"]


def test_reap_blocked_tasks_in_parallel(mock_workflow):
    barrier = threading.Barrier(2, timeout=5)
    two_blocked_groups(mock_workflow, lambda group_id: barrier.wait())

    assert sorted(mock_workflow.reap_blocked_tasks()) == [
        "group-a-build",
        "group-b-build",
    ]


def test_reap_blocked_tasks_parallel_requests(mock_workflow, monkeypatch):
    two_blocked_groups(mock_workflow, lambda group_id: None)
    monkeypatch.setattr(settings, "taskcluster_parallel_requests", 3)

    with mock.patch(
        "code_review_bot.workflow.ThreadPoolExecutor", wraps=ThreadPoolExecutor
    ) as executor:
        mock_workflow.reap_blocked_tasks()

    executor.assert_called_once_with(max_workers=3)
