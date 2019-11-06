import Vue from 'vue'
import VueRouter from 'vue-router'
import Diffs from './Diffs.vue'
import Revision from './Revision.vue'
import Issues from './Issues.vue'
import Stats from './Stats.vue'
import Check from './Check.vue'

Vue.use(VueRouter)

export default new VueRouter({
  routes: [
    {
      path: '/',
      name: 'diffs',
      component: Diffs
    },
    {
      path: '/D:revisionId',
      name: 'revision',
      component: Revision
    },
    {
      path: '/diff/:diffId',
      name: 'diff',
      component: Issues
    },
    {
      path: '/stats',
      name: 'stats',
      component: Stats
    },
    {
      path: '/check/:check',
      name: 'check',
      component: Check
    }
  ]
})
