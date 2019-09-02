# The default analysis format supported

The [mozlint format](https://github.com/mozilla/code-review/blob/master/bot/code_review_bot/tasks/lint.py#L170) has the following fields for each issue:

* `path` relative to the repository
* `column` & `lineno` where the issue is happening in the file
* `level` (warning | error) of the issue
* `rule`  describing the issue detected (often a unique shorthand code)
* `message` with all the details to provide to the developer
* `linter` if you have multiple analyzers using the same format

Of course you can add other relevant fields to your needs, but these should at least be present (maybe except linter)


Here is an example of an analysis using that format:

```json

```
