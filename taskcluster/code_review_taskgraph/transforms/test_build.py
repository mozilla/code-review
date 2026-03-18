from types import SimpleNamespace

import pytest

from code_review_taskgraph.transforms.build import add_index_routes


def branch_index_route(short_head_ref):
    config = SimpleNamespace(
        params={
            "head_rev": "abc123",
            "head_ref": f"refs/heads/{short_head_ref}",
            "short_head_ref": short_head_ref,
            "tasks_for": "github-push",
        },
        graph_config={"trust-domain": "code-analysis"},
    )
    task = next(add_index_routes(config, [{"name": "bot"}]))
    return task["routes"][-1]


@pytest.mark.parametrize(
    "short_head_ref, expected_branch",
    [
        ("master", "master"),
        ("feature/foo", "feature_foo"),
        (
            "dependabot/pip/backend/sentry-sdk-2.71.0",
            "dependabot_pip_backend_sentry-sdk-2.71.0",
        ),
    ],
)
def test_branch_index_route_replaces_unsupported_characters(
    short_head_ref, expected_branch
):
    assert (
        branch_index_route(short_head_ref)
        == f"index.code-analysis.v2.code-review.bot.branch.{expected_branch}"
    )
