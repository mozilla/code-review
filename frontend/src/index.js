import "bulma/css/bulma.css";
import store from "./store.js";
import router from "./routes.js";
import App from "./App.vue";

import { createApp } from "vue";

const app = createApp(App);
app.use(store);
app.use(router);

app.mount("#root");
