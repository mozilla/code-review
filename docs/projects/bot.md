# Code review Bot

The publication task (or called **bot**) is a Python 3 script, running as a Taskcluster task.

The technical information on how to get started is available in the [project README](/bot/README.md).

## Deployment

The project is built as a Docker in Docker image, on the firefox-ci instance (more information in [CI/CD](/docs/ci-cd/README.md)).

Two hooks are available and configured through [ci-configuration](https://hg.mozilla.org/ci/ci-configuration/file/tip/hooks.yml):

- [project-relman/code-review-production](https://firefox-ci-tc.services.mozilla.com/hooks/project-relman/code-review-production)
- [project-relman/code-review-testing](https://firefox-ci-tc.services.mozilla.com/hooks/project-relman/code-review-testing)

## Workflow

The overall workflow of the publication task is relatively simple:

- The code review hook is triggered by a pulse message, starting a new task for each completed analysis
- List all Taskcluster tasks in the analysis
- Instantiate a task parser for each taskcluster task
- Build issues for each tasks
- Aggregate them
- Publish them on Phabricator

![](bot.png)
[Graph source](bot.mermaid)

### Publishable issues

We publish only a subset of issues detected:

- every **Error** is reported, no matter where it's detected.
- **Warnings** that are inside the patch (modified lines of files in patch) are reported

Other warnings are discarded (but still reportted in debug & backend mode)

## Supported tasks

Each analyzer must be supported by the bot, in order to convert the JSON artifacts into a list of issues.

The first half part of the workflow is to convert JSON files into a list of `code_review_bot.Issue` sub classes instances.

Each `code_review_bot.Issue` has a common interface to build Phabricator LintResult and comments (amongst other outputs).

### Clang-Tidy

This support task `source-test-clang-tidy` from Mozilla central, and parses the custom artifact `public/code-review/clang-tidy.json`.

It will output a list of `ClangTidyIssue`, reporting static analysis warnings. A few extra filtering rules are present.

### Clang-Format

This support task `source-test-clang-format` from Mozilla central, and parses the custom artifact `public/code-review/clang-tidy.diff`. (Only task to use a diff directly)

It will output a list of `ClangFormatIssue`, reporting formatting warnings, with fixes provided to the developer.

### Coverity

This support the Coverity integration Mozilla Central and NSS, and parses the custom artifact `public/code-review/coverity.json`.

It will output a list of `CoverityIssue`, reporting static analysis warnings and build errors.

### Infer

This support the `source-test-infer` from Mozilla Central, and parses the custom artifact `public/code-review/infer.json`.

It will output a list of `InferIssue` reporting static analysis and formatting issues in Java source code.

### Mozlint

This support all the Mozlint tasks (and there are a lot!) from Mozilla central. It parses the custom artifact and mozlint json format defined in `public/code-review/mozlint.json`.

It will output a list of `MozLintIssue` reporting on various issues for most languages in Mozilla central.

### Default format

We also built a default task support & format, described in extensive details [here](/docs/analysis_format.md).

This format should be used by new analyzers, as this does not require any change in the bot !

## Reporters

The publication task support several reporters to publish issues. They are defined in the shared [configuration](/docs/configuration.md).

### Phabricator

This is definitely the most important reporter. It will publish all issues deemed publishable on the Phabricator revision & build being analysed.

We publish two things (when issues are published):
- a summary comment listing the number of issues found, their type, and some help text
- one **LintResult** per issue found.

For more information, read the [phabricator](/docs/phabricator.md) documentation.

### Debug

The debug reporter lists all the issue in a public JSON artifact and send an email to admins with the full list of issues.

It could be deprecated now that we have better tracking and management of issues (it was the first reporter created, a long time ago).

### Build error

Build errors are really bad, and we want to send an email to the developer when they occur. So this reporter simply send an email to the developer using Taskcluster notification system.

### Backend

The backend has no reporter as it's more tightly coupled to the bot system, but every issue is published on the backend.

Each Issue also has a unique hash calculated, using the modified lines source code, the issue summary. It's used to be able to compare issues together.
