import Vue from "vue";
import "bulma/css/bulma.css";
import App from "./App.vue";
import store from "./store.js";
import router from "./routes.js";

// Load chartist from the vue plugin
// but the stylesheet directly
import Chartist from "vue-chartist";
import "chartist/dist/chartist.css";
Vue.use(Chartist);

export default new Vue({
  store,
  router,
  el: "#root",
  render: (h) => h(App),
});
