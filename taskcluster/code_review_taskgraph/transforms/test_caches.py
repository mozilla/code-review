from types import SimpleNamespace

import pytest

from code_review_taskgraph.transforms.caches import disable_caches_for_untrusted


def transform_tasks(tasks_for, tasks):
    config = SimpleNamespace(params={"tasks_for": tasks_for})
    return list(disable_caches_for_untrusted(config, tasks))


def test_untrusted_run_tasks_do_not_use_caches():
    tasks = transform_tasks(
        "github-pull-request-untrusted",
        [{"name": "test-bot", "run": {"using": "run-task"}}],
    )

    assert tasks[0]["run"]["use-caches"] is False


@pytest.mark.parametrize(
    "tasks_for", ["github-pull-request", "github-push", "github-release"]
)
def test_trusted_run_tasks_keep_default_caches(tasks_for):
    tasks = transform_tasks(
        tasks_for, [{"name": "test-bot", "run": {"using": "run-task"}}]
    )

    assert "use-caches" not in tasks[0]["run"]


def test_untrusted_tasks_without_run_are_unchanged():
    tasks = transform_tasks("github-pull-request-untrusted", [{"name": "docker-image"}])

    assert tasks == [{"name": "docker-image"}]
