# The default analysis format

Each analysis **must** build a JSON Taskcluster artifact publicly available, containing all the issues detected on the patch.

The file **must** be available as `public/code-review/issues.json`.

The [default format](https://github.com/mozilla/code-review/blob/1.0.5/bot/code_review_bot/tasks/default.py#L170) (loosely based on Mozlint format) has the following fields for each issue:

* `path` **relative** to the repository
* `column` & `line` where the issue is happening in the file. They must be positive integers, or `null` when unknown or for a full file.
* `nb_lines` (optional) is a positive integer when your issue spans across several lines. It will default to 1 line.
* `level` (warning | error) of the issue
* `check`  describing the issue detected (often a unique shorthand code)
* `message` with all the details to provide to the developer
* `analyzer` (optional) if you have multiple analyzers using the same format. It will default to the task name.

The issues should be grouped by relative paths, as a list of issues per file.

:warning: You need to provide relative paths to the repository. The bot does not support any absolute path resolution as it's not using the same setup as your own task.

Here is an example of an analysis using this format:

```json
{
  "path/to/file.py": [
    {
      "path": "path/to/file.py",
      "line": 51,
      "nb_lines": 1,
      "column": 42,
      "check": "bad_issue.XXX123",
      "level": "error",
      "message": "This is a really bad issue in your code",
      "analyzer": "python_analyzer"
    }
  ]
}
```

To have more information about Mozlint, please see the [mozlint documentation](https://firefox-source-docs.mozilla.org/tools/lint/index.html)
