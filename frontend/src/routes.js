import Vue from 'vue'
import VueRouter from 'vue-router'
import Diffs from './Diffs.vue'
import Diff from './Diff.vue'
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
      path: '/rev/:revision',
      name: 'revision',
      component: Diffs
    },
    {
      path: '/diff/:diffId',
      name: 'diff',
      component: Diff
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
