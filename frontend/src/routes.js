import Diffs from "./Diffs.vue";
import Tasks from "./Tasks.vue";
import Revision from "./Revision.vue";
import Issues from "./Issues.vue";
import Stats from "./Stats.vue";
import Check from "./Check.vue";

import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/",
    name: "diffs",
    component: Diffs,
  },
  {
    path: "/tasks",
    name: "tasks",
    component: Tasks,
  },
  {
    path: "/revision/:revisionId",
    name: "revision",
    component: Revision,
  },
  {
    path: "/diff/:diffId",
    name: "diff",
    component: Issues,
  },
  {
    path: "/stats",
    name: "stats",
    component: Stats,
  },
  {
    path: "/check/:repository/:analyzer/:check",
    name: "check",
    component: Check,
  },
];

const router = createRouter({
  routes,
  history: createWebHistory(),
});

export default router;
