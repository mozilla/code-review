# How to add a new analyzer on the code review bot

## Requirements

1. Your repository must use [Mozilla Phabricator's instance](https://phabricator.services.mozilla.com/)
2. Your repository must use [Taskcluster as CI](https://docs.taskcluster.net) (at least one task must start on each push).
3. You are adding a Taskcluster task that runs on each push, analyzes the modified source code and lists potential issues.

## Build analysis output

The code-review bot currently supports 6 different formats to report issues (clang-tidy, clang-format, zero coverage, coverity, infer and mozlint).
We are in the process of standardizing toward [a single format described here](analysis_format.md).

New analyzers are strongly encouraged to use that format, as it's supported directly in the bot. Other formats, or more detailed versions will need an update in the bot's code itself.


### Taskcluster artifacts

Your analyzer task needs to produce a [public Taskcluster artifact] listing all the issues found in the patch.

That means your task **must** write a JSON file on the local file system at a specified path. The task definition will take care of configuring Taskcluster for the storage of your file, so it becomes a publicly available file online.

Here is [an example implementation](https://hg.mozilla.org/mozilla-central/file/tip/taskcluster/ci/source-test/clang.yml#l58) from the `clang-tidy` task in mozilla-central:

```yaml
worker:
  artifacts:
    - type: file
      name: public/code-review/clang-tidy.json
      path: /builds/worker/clang-tidy.json
```

Here, the analyzer produces its JSON output as `/builds/worker/clang-tidy.json`, but Taskcluster will expose it on its own public hostname as `https://taskcluster-artifacts.net/<TASK_ID>/<RUN_ID>/public/code-review/clang-tidy.json`

## Add code-review

:warning: This step is specific to mozilla-central and its taskgraph. Other repositories have different decision tasks & mechanisms.

Once your task is setup in the repository taskgraph, usually in [taskcluster/ci/source-test](https://github.com/mozilla/release-services/issues/2254), you'll need to add an attribute to the task definition so the code-review bot will automatically start your task on new diffs.

It's simple to add:

```yaml
attributes:
  code-review: true
```

Here is an example for [clang tasks](https://hg.mozilla.org/mozilla-central/file/tip/taskcluster/ci/source-test/clang.yml#l12)

## Publish results on Phabricator

Once your task is triggered with the `code-review` attribute, its analysis artifact should be retrieved automatically by the bot if you use the default format.

If you produce a different format, this will need a specific implementation on the bot (:mag: doc needed here)

The bot will retrieve all issues from your artifact, and filter them using basic rules:

* if the issue is not in a modifided line of a file in the patch, it will be discarded.
* if the issue is in a third party path, it will be discarded.

We have [plans](https://bugzilla.mozilla.org/show_bug.cgi?id=1555721) to remove the first filter, by using a two pass approach and comparing the issues found before vs. after applying the patch.


## Troubleshooting

1. Check that your task is triggered by the decision task on new diffs
2. Check that your task is present in the task group published by the code review bot as `Treeherder jobs`
3. Check that your task produces the expected analysis artifact
4. Check that the `code-review-issues` is present in that task group (for mozilla-central tasks)
5. Check that your test diff is available on [our dashboard](https://static-analysis.moz.tools/) by searching its revision ID or title (it can take several seconds to load all the tasks available)
6. Reach out to developers on Slack #code-review-bot
