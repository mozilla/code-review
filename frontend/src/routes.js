import Vue from 'vue'
import VueRouter from 'vue-router'
import Tasks from './Tasks.vue'
import Task from './Task.vue'
import Stats from './Stats.vue'
import Check from './Check.vue'

Vue.use(VueRouter)

export default new VueRouter({
  routes: [
    {
      path: '/',
      name: 'tasks',
      component: Tasks
    },
    {
      path: '/task/:taskId',
      name: 'task',
      component: Task
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
