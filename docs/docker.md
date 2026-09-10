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

## Upgrade an existing PostgreSQL database

The PostgreSQL data is stored through a Docker volume. To avoid any data loss, we advice to save a copy of the volume before following the below instructions. The volume is usually located at `/var/lib/docker/volumes/code-review_pgdata/`.

We recommend performing the update using `pg_dump`, as it simplifies handling multiple major PostgreSQL updates.
Make sure you ran all the latest migrations and checked out to the latest version before continuing.

1. Back up the existing data using `pg_dump`

```sh=
docker run -d --rm --name=old-database \
    -e POSTGRES_PASSWORD=devdata \
    -e POSTGRES_USER=devuser \
    -e POSTGRES_DB=code_review_dev \
    -v code-review_pgdata:/var/lib/postgresql/data -p 127.0.0.1:5432:5432 postgres:<old_version>-alpine
PGPASSWORD=devdata pg_dump -h localhost -p 5432 -U devuser -d code_review_dev > dump.sql
```

There should be no error and the size of `dump.sql` should be approximately the size of the volume.

2. ⚠ Trash the previously used volume:

```sh=
docker kill old-database
docker volume rm code-review_pgdata
```

You will need to kill all database access first. In case docker complains about a container using the volume, you may also have to delete the container first:

```sh=
docker rm <container_id>
```

3. You can then run the up-to-date PostgreSQL via `docker-compose.yml` and restore the data:

```sh=
docker compose up db -d
docker exec code-review-db postgres -V # Should return the latest PostgreSQL version
PGPASSWORD=devdata psql --user=devuser --host=localhost -d code_review_dev < dump.sql
```

4. Check the application runs as expected by starting a development server: all your data should be there.

5. ⚠ Cleanup the local file used for the dump:

```sh=
rm dump.sql
```
