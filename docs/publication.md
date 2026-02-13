# How to publish issues on Phabricator

## Build analysis output

The code-review bot currently supports 6 different formats to report issues (clang-tidy, clang-format, zero coverage and mozlint).
We are in the process of standardizing toward [a single format described here](analysis_format.md).

### Taskcluster artifacts

Your analyzer task needs to produce a public Taskcluster artifact listing all the issues found in the patch.

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

## Publish results

Once your task is triggered with the `code-review` attribute, its analysis artifact will be retrieved automatically by the bot. All issues found will be filtered using those basic rules:

- if the issue is not in a modifided line of a file in the patch, it will be discarded.
- if the issue is in a third party path, it will be discarded.

The bot supports publishing a review to either a Phabricator revision or a Github pull request.

## Troubleshooting

1. Check that your task is triggered by the decision task on new diffs
2. Check that your task is present in the task group published by the code review bot as `CI (Treeherder) Jobs`
3. Check that your task produces the expected analysis artifact
4. Check that the `code-review-issues` is present in that task group (for mozilla-central tasks)
5. Check that your test diff is available on [our dashboard](https://code-review.moz.tools/) by searching its revision ID or title (it can take several seconds to load all the tasks available)
6. Reach out to us, see [README](../README.md) for contact info
