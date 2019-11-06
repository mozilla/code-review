<script>
export default {
  mounted () {
    this.$store.dispatch('load_revision', { id: this.$route.params.revisionId })
      .then(resp => { this.$set(this, 'state', 'loaded') })
      .catch(err => { this.$set(this, 'state', err) })
  },
  data () {
    return {
      state: 'loading'
    }
  },
  computed: {
    revision () {
      return this.$store.state.revision
    }
  }
}
</script>

<template>
  <section>
    <h1 class="title">Revision D{{ $route.params.revisionId }}</h1>

    <div class="notification is-info" v-if="state == 'loading'">Loading...</div>
    <div v-else-if="state == 'loaded'">
      <h2 class="subtitle">{{ revision.title }}</h2>
      <p>
        On <strong>{{ revision.repository }}</strong> - <a :href="revision.phabricator_url" target="_blank">View on Phabricator</a>
        <span v-if="revision.bugzilla_id">
          - <a :href="'https://bugzil.la/' + revision.bugzilla_id" target="_blank">View Bug {{ revision.bugzilla_id }}</a>
        </span>
      </p>

      <div v-for="diff in revision.diffs">
        <router-link :to="{ name: 'diff', params: { diffId: diff.id }}" class="button is-primary">Diff {{ diff.id }}</router-link>
      </div>
    </div>
    <div class="notification is-danger" v-else>
      <h4 class="title">Error</h4>
      {{ state }}
    </div>
  </section>
</template>
