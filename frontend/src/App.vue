<script>
export default {
  name: 'App',
  computed: {
    backend_url () {
      return this.$store.state.backend_url
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
            <div class="navbar-item">Code Review Bot</div>
          </div>
          <div class="navbar-menu">

            <div class="navbar-start">
              <div class="navbar-item">
                <span class="navbar-item">Connected to {{ backend_url }}</span>
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
      <a href="https://github.com/mozilla/code-review/tree/master/frontend" target="_blank">Source Code</a>
      <span>&bull;</span>
      <a href="https://github.com/mozilla/code-review/issues" target="_blank">Report an issue</a>
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
