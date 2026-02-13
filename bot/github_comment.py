#!python
import sys

from code_review_bot.report.github import GithubReporter
from code_review_bot.revisions import GithubRevision
from code_review_bot.tasks.clang_tidy import ClangTidyIssue, ClangTidyTask


def get_configuration():
    """
    The configuration is directly set from command line arguments, in order to ease developments.

    Example of code review reporter configuration to publish on github API:
    ```
    bot:
      REPORTERS:
        - reporter: github
          app_client_id: xxxxxxxxxxxxxxxxxxxx
          app_pem_file: path/to.pem
          app_installation_id: 123456789
    ```
    """
    _, *args = sys.argv
    if not len(args) == 3:
        raise RuntimeError(
            "Please run this script with 3 arguments:\n"
            "* App client ID (xxxxxxxxxxxxxxxxxxxx)\n"
            "* Path to Github private key (`.pem` file)\n"
            "* App installation ID (123456789)"
        )

    app_client_id, app_secret, app_installation_id = args
    assert len(app_client_id) == 20, "Github App client ID should be 20 characters."
    assert (
        app_installation_id.isdigit()
    ), "Installation ID should be composed of digits."
    return {
        "reporter": "github",
        "app_client_id": app_client_id,
        "app_pem_file": app_secret,
        "app_installation_id": app_installation_id,
    }


def mock_task(cls, name):
    """Build configuration for any Analysis task"""
    return cls(f"{name}-ID", {"task": {"metadata": {"name": name}}, "status": {}})


def main():
    """
    Initialize a Github reporter and publish issues
    """
    reporter = GithubReporter(get_configuration())
    revision = GithubRevision(
        repo_url="https://github.com/vrigal/test-dev-mozilla",
        branch="reporter-demo",
        pull_head_sha="da4ed2eccaff01034c1c2091d2797d55bc0c57cf",
        pull_number=3,
    )

    analyzer = mock_task(ClangTidyTask, "source-test-clang-tidy")
    issue1 = ClangTidyIssue(
        analyzer,
        revision,
        "a_first_test.cpp",
        "1",
        "1",
        "parser-error",
        "Reporter: this file is not C++ !",
    )
    issue2 = ClangTidyIssue(
        analyzer,
        revision,
        "another_test.cpp",
        "11",
        "11",
        "no-line-after-return",
        "Dummy message",
    )
    # Mock all issues as publishable
    issue1.is_publishable = lambda: True
    issue2.is_publishable = lambda: True

    reporter.publish(
        [issue1, issue2], revision, task_failures=[], notices=[], reviewers=[]
    )


if __name__ == "__main__":
    main()
