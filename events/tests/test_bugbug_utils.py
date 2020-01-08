# -*- coding: utf-8 -*-
import asyncio
import json
import os

import pytest
import responses
from libmozdata.phabricator import UnitResultState
from libmozevent.bus import MessageBus
from libmozevent.phabricator import PhabricatorBuild

from code_review_events import QUEUE_PHABRICATOR_RESULTS
from code_review_events import taskcluster_config
from code_review_events.bugbug_utils import BugbugUtils


class MockURL:
    def __init__(self, **kwargs):
        self.query = kwargs


class MockRequest:
    def __init__(self, **kwargs):
        self.rel_url = MockURL(**kwargs)


@pytest.mark.asyncio
async def test_risk_analysis_should_trigger(PhabricatorMock, mock_taskcluster):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    with PhabricatorMock as phab:
        phab.load_patches_stack(build)
        phab.update_state(build)

        # Reviewer of the patch is in the list of risk analysis users.
        taskcluster_config.secrets = {
            "risk_analysis_users": ["ehsan", "heycam"],
            "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
        }

        bugbug_utils = BugbugUtils(phab.api)
        bugbug_utils.register(bus)

        assert bugbug_utils.should_run_risk_analysis(build)

        # Author of the patch is in the list of risk analysis users.
        taskcluster_config.secrets = {
            "risk_analysis_users": ["ehsan", "tnguyen"],
            "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
        }

        bugbug_utils = BugbugUtils(phab.api)

        assert bugbug_utils.should_run_risk_analysis(build)


@pytest.mark.asyncio
async def test_risk_analysis_shouldnt_trigger(PhabricatorMock, mock_taskcluster):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    taskcluster_config.secrets = {
        "risk_analysis_users": ["ehsan"],
        "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
    }

    with PhabricatorMock as phab:
        phab.load_patches_stack(build)
        phab.update_state(build)

        bugbug_utils = BugbugUtils(phab.api)
        bugbug_utils.register(bus)

    assert not bugbug_utils.should_run_risk_analysis(build)


@pytest.mark.asyncio
async def test_should_run_test_selection(PhabricatorMock, mock_taskcluster):
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    def calc_perc():
        count = sum(
            1 for _ in range(1000) if bugbug_utils.should_run_test_selection(build)
        )
        return count / 1000

    with PhabricatorMock as phab:
        phab.load_patches_stack(build)
        phab.update_state(build)

        bugbug_utils = BugbugUtils(phab.api)

        taskcluster_config.secrets = {
            "test_selection_enabled": False,
            "test_selection_share": 0.0,
        }

        bugbug_utils = BugbugUtils(phab.api)
        assert calc_perc() == 0.0

        taskcluster_config.secrets = {
            "test_selection_enabled": False,
            "test_selection_share": 0.0,
            "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
        }

        bugbug_utils = BugbugUtils(phab.api)
        assert calc_perc() == 0.0

        taskcluster_config.secrets = {
            "test_selection_enabled": True,
            "test_selection_share": 0.0,
            "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
        }

        bugbug_utils = BugbugUtils(phab.api)
        assert calc_perc() == 0.0

        taskcluster_config.secrets = {
            "test_selection_enabled": True,
            "test_selection_share": 0.1,
            "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
        }

        bugbug_utils = BugbugUtils(phab.api)
        assert 0.03 < calc_perc() < 0.18


@pytest.mark.asyncio
async def test_process_push(PhabricatorMock, mock_taskcluster):
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )
    with PhabricatorMock as phab:
        phab.load_patches_stack(build)
        phab.update_state(build)
        phab.load_reviewers(build)

        bugbug_utils = BugbugUtils(phab.api)

        try:
            await bugbug_utils.diff_to_push.rem(str(build.diff_id))
        except KeyError:
            pass

        with pytest.raises(KeyError):
            await bugbug_utils.diff_to_push.get(str(build.diff_id))

        await bugbug_utils.process_push(
            (
                "success",
                build,
                {
                    "treeherder_url": "https://treeherder.mozilla.org/#/jobs?repo=try&revision=123",
                    "revision": "123",
                },
            )
        )

        assert await bugbug_utils.diff_to_push.get(str(build.diff_id)) == {
            "revision": "123",
            "treeherder_url": "https://treeherder.mozilla.org/#/jobs?repo=try&revision=123",
            "build": build,
        }

        if "REDIS_URL" in os.environ:
            # Simulate a restart.
            bugbug_utils = BugbugUtils(phab.api)

            stored_push = await bugbug_utils.diff_to_push.get(str(build.diff_id))
            assert stored_push["revision"] == "123"
            assert (
                stored_push["treeherder_url"]
                == "https://treeherder.mozilla.org/#/jobs?repo=try&revision=123"
            )
            assert stored_push["build"].diff_id == build.diff_id
            assert stored_push["build"].target_phid == build.target_phid


@pytest.mark.asyncio
async def test_got_bugbug_test_select_end(PhabricatorMock, mock_taskcluster):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    diffId = str(build.diff_id)

    payload = {
        "routing": {
            "exchange": "exchange/taskcluster-queue/v1/task-completed",
            "key": "primary.OhtlizLqT9ah2jVkUL-yvg.0.community-tc-workers-google.8155538221748661937.proj-relman.compute-large.-.OhtlizLqT9ah2jVkUL-yvg._",
            "other_routes": [
                b"route.notify.email.release-mgmt-analysis@mozilla.com.on-failed",
                b"route.notify.irc-channel.#bugbug.on-failed",
                b"route.index.project.relman.bugbug.test_select.latest",
                f"route.index.project.relman.bugbug.test_select.diff.{diffId}".encode(),
                b"route.project.relman.bugbug.test_select",
            ],
        },
        "body": {
            "status": {
                "taskId": "bugbug-test-select",
                "provisionerId": "proj-relman",
                "workerType": "compute-large",
                "schedulerId": "-",
                "taskGroupId": "HDnvYOibTMS8h_5Qzv6fWg",
                "deadline": "2019-11-27T17:03:07.100Z",
                "expires": "2019-12-27T15:03:07.100Z",
                "retriesLeft": 5,
                "state": "completed",
                "runs": [
                    {
                        "runId": 0,
                        "state": "completed",
                        "reasonCreated": "scheduled",
                        "reasonResolved": "completed",
                        "workerGroup": "community-tc-workers-google",
                        "workerId": "8155538221748661937",
                        "takenUntil": "2019-11-27T15:25:02.767Z",
                        "scheduled": "2019-11-27T15:03:07.606Z",
                        "started": "2019-11-27T15:05:02.786Z",
                        "resolved": "2019-11-27T15:19:24.809Z",
                    }
                ],
            },
            "runId": 0,
            "task": {"tags": {}},
            "workerGroup": "community-tc-workers-google",
            "workerId": "8155538221748661937",
            "version": 1,
        },
    }

    taskGroupId = payload["body"]["status"]["taskGroupId"]

    taskcluster_config.secrets = {
        "test_selection_enabled": True,
        "test_selection_share": 0.1,
        "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
    }

    with PhabricatorMock as phab:
        phab.load_patches_stack(build)
        phab.update_state(build)

        bugbug_utils = BugbugUtils(phab.api)
        bugbug_utils.register(bus)

    try:
        await bugbug_utils.diff_to_push.rem(diffId)
    except KeyError:
        pass

    try:
        await bugbug_utils.task_group_to_push.rem(taskGroupId)
    except KeyError:
        pass

    # Nothing happens when diff_to_push is empty.
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select",
            body=mock_taskcluster("task-bugbug-test-select.json"),
            content_type="application/json",
        )

        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select/artifacts/public%2Ffailure_risk",
            body=mock_taskcluster("artifact-bugbug-test-select-failure-risk"),
        )

        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select/artifacts/public%2Fselected_tasks",
            body=mock_taskcluster("artifact-bugbug-test-select-selected-tasks"),
        )

        with pytest.raises(KeyError):
            await bugbug_utils.diff_to_push.get(diffId)
        await bugbug_utils.got_bugbug_test_select_end(payload)
        with pytest.raises(KeyError):
            await bugbug_utils.task_group_to_push.get(taskGroupId)

    # Nothing happens when the failure risk is low.
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select",
            body=mock_taskcluster("task-bugbug-test-select.json"),
            content_type="application/json",
        )

        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select/artifacts/public%2Ffailure_risk",
            body=mock_taskcluster("artifact-bugbug-test-select-failure-risk-0"),
        )

        await bugbug_utils.diff_to_push.set(diffId, {"revision": "123", "build": build})
        await bugbug_utils.got_bugbug_test_select_end(payload)
        with pytest.raises(KeyError):
            await bugbug_utils.task_group_to_push.get(taskGroupId)
        # Wait removal of object from diff_to_push to be done.
        tasks = set(asyncio.all_tasks())
        tasks.remove(asyncio.current_task())
        await asyncio.gather(*tasks)
        with pytest.raises(KeyError):
            await bugbug_utils.diff_to_push.get(diffId)

    # Nothing happens when the failure risk is high but there are no selected tasks.
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select",
            body=mock_taskcluster("task-bugbug-test-select.json"),
            content_type="application/json",
        )

        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select/artifacts/public%2Ffailure_risk",
            body=mock_taskcluster("artifact-bugbug-test-select-failure-risk"),
        )

        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select/artifacts/public%2Fselected_tasks",
            body=mock_taskcluster("artifact-bugbug-test-select-selected-tasks-none"),
        )

        await bugbug_utils.diff_to_push.set(diffId, {"revision": "123", "build": build})
        await bugbug_utils.got_bugbug_test_select_end(payload)
        with pytest.raises(KeyError):
            await bugbug_utils.task_group_to_push.get(taskGroupId)
        # Wait removal of object from diff_to_push to be done.
        tasks = set(asyncio.all_tasks())
        tasks.remove(asyncio.current_task())
        await asyncio.gather(*tasks)
        with pytest.raises(KeyError):
            await bugbug_utils.diff_to_push.get(diffId)

    # Stuff happens.
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select",
            body=mock_taskcluster("task-bugbug-test-select.json"),
            content_type="application/json",
        )

        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select/artifacts/public%2Ffailure_risk",
            body=mock_taskcluster("artifact-bugbug-test-select-failure-risk"),
        )

        rsps.add(
            responses.GET,
            "http://community_taskcluster.test/api/queue/v1/task/bugbug-test-select/artifacts/public%2Fselected_tasks",
            body=mock_taskcluster("artifact-bugbug-test-select-selected-tasks"),
        )

        rsps.add(
            responses.GET,
            "http://taskcluster.test/api/index/v1/task/gecko.v2.try.revision.123.taskgraph.decision",
            body=mock_taskcluster("index-gecko-decision.json"),
            content_type="application/json",
        )

        rsps.add(
            responses.GET,
            f"http://taskcluster.test/api/queue/v1/task/{taskGroupId}/artifacts/public%2Factions.json",
            body=mock_taskcluster("artifact-gecko-decision-actions.json"),
            content_type="application/json",
        )

        def trigger_hook_callback(request):
            payload = json.loads(request.body)
            assert payload == json.loads(
                mock_taskcluster("trigger-hook-add-new-jobs-post-body.json")
            )
            return (
                200,
                {"Content-Type": "application/json"},
                mock_taskcluster("trigger-hook-add-new-jobs.json"),
            )

        rsps.add_callback(
            responses.POST,
            "http://taskcluster.test/api/hooks/v1/hooks/project-gecko/in-tree-action-1-generic%2Fea5d85cbef/trigger",
            callback=trigger_hook_callback,
        )

        push = {"revision": "123", "build": build}
        await bugbug_utils.diff_to_push.set(diffId, push)
        await bugbug_utils.got_bugbug_test_select_end(payload)
        assert await bugbug_utils.task_group_to_push.get(taskGroupId) == push
        # Wait removal of object from diff_to_push to be done.
        tasks = set(asyncio.all_tasks())
        tasks.remove(asyncio.current_task())
        await asyncio.gather(*tasks)
        with pytest.raises(KeyError):
            await bugbug_utils.diff_to_push.get(diffId)


@pytest.mark.asyncio
async def test_got_try_task_end(PhabricatorMock, mock_taskcluster, mock_treeherder):
    bus = MessageBus()
    build = PhabricatorBuild(
        MockRequest(
            diff="125397",
            repo="PHID-REPO-saax4qdxlbbhahhp2kg5",
            revision="36474",
            target="PHID-HMBT-icusvlfibcebizyd33op",
        )
    )

    payload = {
        "routing": {
            "exchange": "exchange/taskcluster-queue/v1/task-completed",
            "key": "primary.fUAKaIdkSF6K1NlOgx7-LA.0.aws.i-0a45c84b1709af6a7.gecko-t.t-win10-64.gecko-level-1.RHY-YSgBQ7KlTAaQ5ZWP5g._",
            "other_routes": [
                b"route.tc-treeherder.v2.try.028980a035fb3e214f7645675a01a52234aad0fe.455891"
            ],
        },
        "body": {
            "status": {
                "taskId": "W2SMZ3bYTeanBq-WNpUeHA",
                "provisionerId": "gecko-t",
                "workerType": "t-linux-xlarge",
                "schedulerId": "gecko-level-1",
                "taskGroupId": "HDnvYOibTMS8h_5Qzv6fWg",
                "deadline": "2019-11-23T14:04:41.581Z",
                "expires": "2019-12-06T14:04:41.581Z",
                "retriesLeft": 5,
                "state": "completed",
                "runs": [
                    {
                        "runId": 0,
                        "state": "completed",
                        "reasonCreated": "scheduled",
                        "reasonResolved": "completed",
                        "workerGroup": "aws",
                        "workerId": "i-01a6b2a05e2211f7c",
                        "takenUntil": "2019-11-22T15:51:57.083Z",
                        "scheduled": "2019-11-22T15:31:56.661Z",
                        "started": "2019-11-22T15:31:57.162Z",
                        "resolved": "2019-11-22T15:42:46.684Z",
                    }
                ],
            },
            "runId": 0,
            "task": {
                "tags": {
                    "kind": "test",
                    "worker-implementation": "docker-worker",
                    "createdForUser": "ttung@mozilla.com",
                    "retrigger": "true",
                    "label": "test-linux64-shippable/opt-awsy-tp6-e10s",
                    "os": "linux",
                }
            },
            "workerGroup": "aws",
            "workerId": "i-01a6b2a05e2211f7c",
            "version": 1,
        },
    }

    taskGroupId = payload["body"]["status"]["taskGroupId"]

    taskcluster_config.secrets = {
        "test_selection_enabled": True,
        "test_selection_share": 0.1,
        "taskcluster_community": {"client_id": "xxx", "access_token": "yyy"},
    }

    with PhabricatorMock as phab:
        bus.add_queue(QUEUE_PHABRICATOR_RESULTS)

        phab.load_patches_stack(build)
        phab.update_state(build)
        phab.load_reviewers(build)

        bugbug_utils = BugbugUtils(phab.api)
        bugbug_utils.register(bus)

    try:
        await bugbug_utils.task_group_to_push.rem(taskGroupId)
    except KeyError:
        pass

    # Nothing happens for tasks that are not test tasks.
    payload["body"]["task"]["tags"]["kind"] = "source-test"
    await bugbug_utils.got_try_task_end(payload)
    assert bus.queues[QUEUE_PHABRICATOR_RESULTS].empty()

    # Nothing happens for tasks that are not registered.
    payload["body"]["task"]["tags"]["kind"] = "test"
    await bugbug_utils.got_try_task_end(payload)
    assert bus.queues[QUEUE_PHABRICATOR_RESULTS].empty()

    push = {
        "build": build,
        "revision": "028980a035fb3e214f7645675a01a52234aad0fe",
    }
    await bugbug_utils.task_group_to_push.set(taskGroupId, push)

    payload["body"]["status"]["state"] = "completed"
    await bugbug_utils.got_try_task_end(payload)
    mode, build_, extras = await bus.receive(QUEUE_PHABRICATOR_RESULTS)
    assert mode == "test_result"
    assert build_ == build
    assert extras == {
        "name": "test-linux64-shippable/opt-awsy-tp6-e10s",
        "result": UnitResultState.Pass,
        "details": None,
    }

    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(
            responses.GET,
            "https://treeherder.mozilla.org/api/jobdetail/?job_guid=5b648c67-76d8-4de6-a706-af9636951e1c/0",
            body=mock_treeherder("jobdetail.json"),
            content_type="application/json",
        )

        payload["body"]["status"]["state"] = "failed"
        await bugbug_utils.got_try_task_end(payload)
        mode, build_, extras = await bus.receive(QUEUE_PHABRICATOR_RESULTS)
        assert mode == "test_result"
        assert build_ == build
        assert extras == {
            "name": "test-linux64-shippable/opt-awsy-tp6-e10s",
            "result": UnitResultState.Fail,
            "details": "https://treeherder.mozilla.org/#/jobs?repo=try&revision=028980a035fb3e214f7645675a01a52234aad0fe&selectedJob=277665740",
        }

    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(
            responses.GET,
            "https://treeherder.mozilla.org/api/jobdetail/?job_guid=5b648c67-76d8-4de6-a706-af9636951e1c/0",
            body=mock_treeherder("jobdetail_empty.json"),
            content_type="application/json",
        )

        payload["body"]["status"]["state"] = "failed"
        await bugbug_utils.got_try_task_end(payload)
        mode, build_, extras = await bus.receive(QUEUE_PHABRICATOR_RESULTS)
        assert mode == "test_result"
        assert build_ == build
        assert extras == {
            "name": "test-linux64-shippable/opt-awsy-tp6-e10s",
            "result": UnitResultState.Fail,
            "details": "https://treeherder.mozilla.org/#/jobs?repo=try&revision=028980a035fb3e214f7645675a01a52234aad0fe",
        }
