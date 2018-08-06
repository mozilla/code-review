import Vue from 'vue'
import 'bulma/css/bulma.css'
import App from './App.vue'
import store from './store.js'
import router from './routes.js'

export default new Vue({
  store,
  router,
  el: '#root',
  render: (h) => h(App),
  beforeCreate () {
    this.$store.commit('load_preferences')
  }
})
