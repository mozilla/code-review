# Code Review Frontend

This is a simple Vue.JS administration frontend, the production instance is publicly available at https://code-review.moz.tools/

You'll need Node 16+ to be able to build it.

## Developer setup

```
npm install
npm run build # to build once in production mode
npm run build:dev # to build once in development mode
npm run start # to start a dev server on port 8010
```

## Linting

eslint is available through:

- `npm run lint` to list potential errors,
- `npm run lint:fix` to automatically fix these errors.
