# Code Review Backend

## Developer setup

```
mkvirtualenv -p /usr/bin/python3 code-review-backend
cd backend
pip install -r requirements.txt
./manage migrate
./manage createsuperuser
./manage runserver
./manage loaddata fixtures/repositories.json
```

At this point, you can log into http://127.0.0.1:8000/admin/ with the credentials you mentioned during the `createsuperuser` step.

## Load existing issues

To load remote issues from production (default configuration):

```
./manage load_issues
```

To load already retrieved issues

```
./manage load_issues --offline
```

To load from testing

```
./manage load_issues --environment=testing
```
