# Docker stack

A `docker-compose.yml` file is available to reproduce locally the code-review stack.

Run it with `docker-compose up`

## Restore a backend postgres dump

```bash
pg_restore  -h localhost --user devuser -d code_review_dev path/to/dump
```
