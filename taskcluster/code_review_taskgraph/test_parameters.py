import pytest

from code_review_taskgraph.parameters import decision_parameters


@pytest.mark.parametrize(
    "head_ref, expected_short_head_ref",
    [
        ("refs/heads/master", "master"),
        ("refs/heads/feature/foo", "feature/foo"),
        ("refs/tags/v1.0.0", "v1.0.0"),
        ("v1.11.5", "v1.11.5"),
    ],
)
def test_decision_parameters_keeps_raw_head_ref(head_ref, expected_short_head_ref):
    parameters = {"head_ref": head_ref}

    decision_parameters(None, parameters)

    assert parameters["head_ref"] == head_ref
    assert parameters["short_head_ref"] == expected_short_head_ref
