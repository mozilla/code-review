# The default analysis format

Each analysis **must** build a JSON Taskcluster artifact publicly available, containing all the issues detected on the patch.

The file **must** be available as `public/code-review/issues.json`.

The [default format](https://github.com/mozilla/code-review/blob/1.0.5/bot/code_review_bot/tasks/default.py#L170) (loosely based on Mozlint format) has the following fields for each issue:

- `path` **relative** to the repository
- `column` & `line` where the issue is happening in the file. They must be positive integers, or `null` when unknown or for an issue linked to a full file.
- `nb_lines` (optional) is a positive integer when your issue spans across several lines. It will default to 1 line.
- `level` (warning | error) of the issue
- `check` (optional) describing the issue detected (often a unique shorthand code). It can be optional when the analyzer only produce one type of issues. In that case, the analyzer name will be used instead.
- `message` with all the details to provide to the developer
- `analyzer` (optional) if you have multiple analyzers using the same format. It will default to the task name.

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

We have built a validation tool, available in this repository as `bot/tools/validator.py`. It has no extra dependencies, and can run using any Python version. You can download it directly on your computer to troubleshoot your payloads:

```
wget https://raw.githubusercontent.com/mozilla/code-review/master/bot/tools/validator.py
python validator.py path/to/issues.json
```

If your format is valid, no error should be displayed and the exit status should be `0`. If you encounter an error, you can get more information by adding the `--verbose` (or `-v`) flag to the command line.

To have more information about Mozlint, please see the [mozlint documentation](https://firefox-source-docs.mozilla.org/tools/lint/index.html)
