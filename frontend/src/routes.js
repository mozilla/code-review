import Vue from "vue";
import VueRouter from "vue-router";
import Diffs from "./Diffs.vue";
import Tasks from "./Tasks.vue";
import Revision from "./Revision.vue";
import Issues from "./Issues.vue";
import Stats from "./Stats.vue";
import Check from "./Check.vue";

Vue.use(VueRouter);

export default new VueRouter({
  routes: [
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
<<<<<<< HEAD
      path: "/D:revisionId",
      name: "revision",
      component: Revision,
=======
      path: '/:revisionId',
      name: 'revision',
      component: Revision
>>>>>>> fa65299 (Draft implementation to use optional Phab references on the Revision model)
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
  ],
});
