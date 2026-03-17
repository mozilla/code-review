from typing import Optional

from taskgraph.parameters import extend_parameters_schema
from taskgraph.util.schema import Schema

code_review_schema = Schema.from_dict(
    {
        "channel": Optional[str],
        "backend_url": Optional[str],
        "short_head_ref": Optional[str],
    },
    kw_only=True,
)

extend_parameters_schema(code_review_schema)


def decision_parameters(graph_config, parameters):
    short_head_ref = parameters["head_ref"]
    for prefix in ("refs/heads/", "refs/tags/"):
        if short_head_ref.startswith(prefix):
            short_head_ref = short_head_ref[len(prefix) :]
            break
    parameters["short_head_ref"] = short_head_ref

    if short_head_ref == "testing":
        parameters["channel"] = "testing"
        parameters["backend_url"] = "https://api.code-review.testing.moz.tools"
    elif short_head_ref == "production":
        parameters["channel"] = "production"
        parameters["backend_url"] = "https://api.code-review.moz.tools"
    else:
        parameters["channel"] = "dev"
        parameters["backend_url"] = "https://api.code-review.testing.moz.tools"
