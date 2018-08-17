<script>
import Tasks from './Tasks.vue'

export default {
  name: 'App',
  components: {
    Tasks
  },
  data () {
    return {
      channels: ['testing', 'staging', 'production']
    }
  },
  methods: {
    switch_channel (channel) {
      this.$store.dispatch('switch_channel', channel)
    }
  },
  computed: {
    channel () {
      return this.$store.state.channel
    }
  }
}
</script>

<template>
  <div id="app">
    <main>
      <nav class="navbar is-dark" role="navigation" aria-label="main navigation">
        <div class="container is-fluid">
          <div class="navbar-brand">
            <div class="navbar-item">Static analysis</div>
          </div>
          <div class="navbar-menu">

            <div class="navbar-start">
              <div class="navbar-item has-dropdown is-hoverable">
                <span class="navbar-link">{{ channel }}</span>
                <div class="navbar-dropdown is-boxed">
                  <a class="dropdown-item" v-for="c in channels" :class="{'is-active': c == channel}" v-on:click="switch_channel(c)">
                    {{ c }}
                  </a>
                </div>
              </div>
            </div>

            <div class="navbar-end">
              <div class="navbar-item" v-if="$route.name != 'stats'">
                <router-link to="/stats" class="button is-link">All checks</router-link>
              </div>
              <div class="navbar-item" v-if="$route.name != 'tasks'">
                <router-link to="/" class="button is-link">All tasks</router-link>
              </div>
            </div>
          </div>
        </div>
      </nav>
      <div class="container is-fluid">
        <router-view></router-view>
      </div>
    </main>
    <footer>
      Built by <a href="https://wiki.mozilla.org/Release_Management" target="_blank">Release Management team</a>
      <span>&bull;</span>
      <a href="https://github.com/mozilla/release-services/tree/master/src/staticanalysis/frontend" target="_blank">Source Code</a>
      <span>&bull;</span>
      <a href="https://github.com/mozilla/release-services/issues" target="_blank">Report an issue</a>
    </footer>
  </div>
</template>

<style scoped>
.navbar-brand .navbar-item {
  font-size: 1.1em;
  font-weight: bold;
  color: #a3cc69 !important;
}

div.navbar-item.has-dropdown {
  text-transform: capitalize;
}

/* Bottom footer support, it's not native in Bulma :( */
div#app {
  display: flex;
  min-height: 100vh;
  flex-direction: column;
}

div#app main {
  flex: 1;
}

div#app footer {
  border-top: 1px solid #CCC;
  padding: 2px;
  font-size: 0.9em;
  color: #444;
  background: #EEE;
  text-align: right;
}

div#app footer a:hover {
  text-decoration: underline;
  color: #3273dc;
}

div#app footer span {
  color: #CCC;
}
</style>
