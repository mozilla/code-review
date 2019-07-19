# Mozilla Code Review

This project has 2 parts:

* `bot` is a Python script running as a Taskcluster task, reporting issues found in analyzer tasks,
* `frontend` is an administration frontend (in Vue.js) displaying detailed information about current analyses.

The analyzer tasks are triggered by [pulselistener](https://github.com/mozilla/release-services/tree/master/src/pulselistener), from the release-services project.
