# Docker stack

A `docker-compose.yml` file is available to reproduce locally the code-review stack.

Run it with `docker-compose up`

## Use the backend

A backend instance will be available as http://localhost:8000

You can initialize the database with:

```
docker exec code-review-backend python manage.py migrate
```

You can create an admin account:

```
docker exec -it code-review-backend python manage.py createsuperuser
```

Then you can login on http://localhost:8000/admin/

## Restore a backend postgres dump

The database must be empty (no `migrate`) to be able to restore a backup.

You can download the backup from the Heroku datastore dedicated page.

```bash
export PGPASSWORD=devdata
pg_restore -h localhost --user devuser -d code_review_dev path/to/dump
```
