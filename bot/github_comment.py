#!/usr/bin/env python3
import sys

from code_review_bot.report.github import GithubReporter


def get_configuration():
    """
    Example of code review reporter configuration to publish on github API.

    bot:
      REPORTERS:
        - reporter: github
          app_client_id: xxxxxxxxxxxxxxxxxxxx
          app_pem_file: path/to.pem
    """
    # Handle the GitHub app secret as the single script argument
    _, *args = sys.argv
    assert (
        len(args) == 2
    ), "Please run this script with a App client ID and the path to Github private key (`.pem` file)."
    app_client_id, app_secret, *_ = args
    assert len(app_client_id) == 20, "Github App client ID should be 20 characters."
    return {
        "reporter": "github",
        "app_client_id": app_client_id,
        "app_pem_file": app_secret,
    }


def main():
    """
    Initialize a Github reporter and publish a simple comment on a defined issue
    """
    print("Initializing Github reporter")
    reporter = GithubReporter(get_configuration())
    print("Doing a GET on app/installations")
    data = reporter.github_client.make_request("get", "app/installations")
    print(f"Returned ID: {data[0]['id']}")
    print("Publishing a comment to https://github.com/vrigal/test-dev-mozilla/pull/1")
    reporter.comment(
        owner="vrigal",
        repo="test-dev-mozilla",
        issue_number=1,
        message="test message",
    )


if __name__ == "__main__":
    main()
