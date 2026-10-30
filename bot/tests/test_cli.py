# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from unittest import mock

import pytest
from libmozdata.phabricator import BuildState

from code_review_bot.analysis import AnalysisMode
from code_review_bot.config import settings
from code_review_bot.revisions import PhabricatorRevision, Revision

LINT_FAILURE = "Static analysis and linting did not run due to a generic failure."
BUILD_TEST_FAILURE = "Builds and tests did not run due to a generic failure."


@pytest.fixture
def mock_cli(monkeypatch, mock_taskcluster_config, mock_revision):
    from code_review_bot import cli

    def _setup(analysis_mode, build_test_feature, trigger="analysis", error=None):
        monkeypatch.setattr(
            cli,
            "parse_cli",
            lambda: argparse.Namespace(
                taskcluster_client_id=None,
                taskcluster_access_token=None,
                taskcluster_secret=None,
                configuration=None,
                mercurial_repository=None,
                github_repository=None,
            ),
        )
        monkeypatch.setattr(mock_taskcluster_config, "auth", mock.Mock())
        monkeypatch.setattr(mock_taskcluster_config, "load_secrets", mock.Mock())
        monkeypatch.setattr(
            mock_taskcluster_config, "get_service", lambda name: mock.Mock()
        )
        mock_taskcluster_config.secrets = {
            "APP_CHANNEL": "test",
            "ALLOWED_PATHS": ["*"],
            "repositories": [],
            "ssh_key": None,
            "REPORTERS": [],
            "PHABRICATOR": {
                "api_key": "deadbeef",
                "url": "http://phabricator.test/api/",
                "publish": True,
            },
            "LANDO": {
                "url": "http://lando.test",
                "publish": True,
                "publish_failure": True,
            },
            "ZERO_COVERAGE_ENABLED": False,
            "task_failures_ignored": [],
            "user_blacklist": [],
        }
        monkeypatch.setattr(cli, "init_logger", mock.Mock())
        monkeypatch.setattr(cli, "setup_libmozdata", mock.Mock())
        monkeypatch.setattr(settings, "setup", mock.Mock())
        monkeypatch.setattr(settings, "load_user_blacklist", mock.Mock())
        monkeypatch.setattr(
            settings,
            "phabricator_build_target",
            "PHID-HMBT-test" if trigger == "analysis" else None,
        )
        monkeypatch.setattr(
            settings,
            "try_group_id",
            "remoteTryGroup" if trigger == "publication" else None,
        )
        monkeypatch.setattr(
            settings,
            "generic_group_id",
            "remoteGenericGroup" if trigger == "ingestion" else None,
        )
        monkeypatch.setattr(settings, "analysis_mode", analysis_mode)

        monkeypatch.setattr(
            cli,
            "get_reporters",
            lambda _: {"phabricator": mock.Mock(), "lando": mock.Mock()},
        )
        phabricator_api_cls = mock.Mock()
        monkeypatch.setattr(cli, "PhabricatorAPI", phabricator_api_cls)
        lando_api = mock.Mock()
        lando_api.get_warnings.return_value = []
        monkeypatch.setattr(cli, "LandoWarnings", mock.Mock(return_value=lando_api))
        monkeypatch.setattr(
            cli,
            "downloadArtifactToBuf",
            mock.Mock(return_value=(b"phabricator_diff: PHID-HMBT-test\n", None)),
        )

        workflow = mock.Mock()
        workflow.phabricator_api = phabricator_api_cls.return_value
        if error is not None:
            workflow.start_analysis.side_effect = error
            workflow.run.side_effect = error
            workflow.ingest_revision.side_effect = error
        monkeypatch.setattr(cli, "Workflow", mock.Mock(return_value=workflow))

        monkeypatch.setattr(
            PhabricatorRevision,
            "build_test_feature",
            property(lambda _: build_test_feature),
        )
        mock_revision.id = mock_revision.phabricator_id
        find = mock.Mock(return_value="PHID-HMBT-buildtest")
        monkeypatch.setattr(cli, "find_build_test_target", find)
        workflow.find_build_test_target = find
        from_phabricator_trigger = mock.Mock(return_value=mock_revision)
        monkeypatch.setattr(
            PhabricatorRevision,
            "from_phabricator_trigger",
            staticmethod(from_phabricator_trigger),
        )
        workflow.from_phabricator_trigger = from_phabricator_trigger
        from_try_decision_task = mock.Mock(return_value=mock_revision)
        monkeypatch.setattr(
            Revision,
            "from_try_decision_task",
            staticmethod(from_try_decision_task),
        )
        workflow.from_try_decision_task = from_try_decision_task
        monkeypatch.setattr(
            PhabricatorRevision,
            "from_decision_task",
            staticmethod(mock.Mock(return_value=mock_revision)),
        )

        return cli, workflow, lando_api

    return _setup


@pytest.mark.parametrize("build_test_feature", [False, True])
def test_build_test_trigger(mock_cli, build_test_feature):
    cli, workflow, _ = mock_cli(AnalysisMode.BuildTest, build_test_feature)

    assert cli.main() == 0

    workflow.from_phabricator_trigger.assert_not_called()
    workflow.start_analysis.assert_not_called()
    workflow.update_status.assert_not_called()
    workflow.phabricator.update_build_target.assert_not_called()


@pytest.mark.parametrize("build_test_feature", [False, True])
def test_lint_trigger(mock_cli, mock_revision, build_test_feature):
    cli, workflow, _ = mock_cli(AnalysisMode.Lint, build_test_feature)

    assert cli.main() == 0

    workflow.start_analysis.assert_called_once_with(mock_revision)
    if build_test_feature:
        workflow.find_build_test_target.assert_not_called()
        workflow.phabricator_api.update_build_target.assert_not_called()
    else:
        workflow.find_build_test_target.assert_called_once_with(
            workflow.phabricator_api, "PHID-HMBT-test"
        )
        workflow.phabricator_api.update_build_target.assert_called_once_with(
            "PHID-HMBT-buildtest", BuildState.Pass
        )


@pytest.mark.parametrize(
    "trigger, analysis_mode, build_test_feature, build_target_phid, expected",
    [
        (
            "analysis",
            AnalysisMode.Lint,
            False,
            "PHID-HMBT-test",
            (
                ["", "lint", "build-test"],
                ["PHID-HMBT-test", "PHID-HMBT-buildtest"],
                [LINT_FAILURE, BUILD_TEST_FAILURE],
            ),
        ),
        (
            "analysis",
            AnalysisMode.Lint,
            True,
            "PHID-HMBT-test",
            (
                ["", "lint", "build-test"],
                ["PHID-HMBT-test", "PHID-HMBT-buildtest"],
                [LINT_FAILURE, BUILD_TEST_FAILURE],
            ),
        ),
        (
            "publication",
            AnalysisMode.Lint,
            True,
            "PHID-HMBT-test",
            (["", "lint"], ["PHID-HMBT-test"], [LINT_FAILURE]),
        ),
        (
            "publication",
            AnalysisMode.BuildTest,
            True,
            "PHID-HMBT-buildtest",
            (["build-test"], ["PHID-HMBT-buildtest"], [BUILD_TEST_FAILURE]),
        ),
        (
            "ingestion",
            None,
            True,
            None,
            ([""], [], []),
        ),
    ],
)
def test_failure(
    mock_cli,
    mock_revision,
    trigger,
    analysis_mode,
    build_test_feature,
    build_target_phid,
    expected,
):
    expected_suffixes, expected_targets, expected_warnings = expected
    cli, workflow, lando_api = mock_cli(
        analysis_mode, build_test_feature, trigger=trigger, error=Exception("boom")
    )
    mock_revision.build_target_phid = build_target_phid

    with pytest.raises(Exception, match="boom"):
        cli.main()

    workflow.index.assert_called_once_with(
        mock_revision, namespace_suffixes=expected_suffixes, state="error"
    )
    assert [
        call.args[0] for call in workflow.phabricator.update_build_target.call_args_list
    ] == expected_targets
    assert [
        call.args[0] for call in lando_api.add_warning.call_args_list
    ] == expected_warnings
    assert workflow.find_build_test_target.called is (
        trigger == "analysis"
        or (trigger == "publication" and analysis_mode == AnalysisMode.BuildTest)
    )
    if trigger == "publication":
        assert workflow.from_try_decision_task.call_args.args[1] == (
            "PHID-HMBT-buildtest"
            if analysis_mode == AnalysisMode.BuildTest
            else "PHID-HMBT-test"
        )
