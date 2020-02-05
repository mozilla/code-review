<script>
import Pagination from './Pagination.vue'
import Bool from './Bool.vue'
import Choice from './Choice.vue'

export default {
  mounted () {
    this.load_issues()
  },
  data () {
    return {
      choices: {
        publishable: [
          {
            name: 'All states',
            value: 'all'
          },
          {
            name: 'Publishable',
            value: 'true'
          },
          {
            name: 'Not publishable',
            value: 'false'
          }
        ]
      }
    }
  },
  methods: {
    load_issues (extras) {
      const payload = { ...this.$route.params, ...(extras || {}) }
      this.$store.dispatch('load_check_issues', payload)
    }
  },
  components: {
    Bool,
    Choice,
    Pagination
  },
  computed: {
    issues () {
      if (!this.$store.state.check_issues) {
        return []
      }
      return this.$store.state.check_issues.results
    }
  }
}
</script>

<template>
  <div>
    <h1 class="title">Check {{ $route.params.analyzer }} / {{ $route.params.check }}</h1>
    <h2 class="subtitle">On repository {{ $route.params.repository }}</h2>
    <Pagination :api_data="$store.state.check_issues" name="issues" store_method="load_check_issues"></Pagination>

    <table class="table is-fullwidth" v-if="issues">
      <thead>
        <tr>
          <th>Diff</th>
          <th>Revision</th>
          <th>Path</th>
          <th>Line</th>
          <td><Choice :choices="choices.publishable" name="publishable" v-on:new-choice="load_issues({publishable: $event ? $event.value : 'true'})"/></td>
          <th>Message</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="issue in issues">
          <td>
            {{ issue.diff.id }}
          </td>
          <td>
            <a :href="issue.diff.revision.phabricator_url" target="_blank">D{{ issue.diff.revision.id }}</a>
          </td>
          <td class="mono">{{ issue.path }}</td>
          <td>{{ issue.line }}</td>
          <td>
            <p>
              <span v-if="issue.level == 'error'" class="tag is-danger">Error</span>
              <span v-else-if="issue.level == 'warning'" class="tag is-warning">Warning</span>
              <span v-else class="tag is-dark">{{ issue.level }}</span>
            </p>
            <Bool :value="issue.publishable" name="Publishable" />
            <Bool :value="issue.in_patch" name="In Patch" />
            <Bool :value="issue.new_for_revision" name="New for revision" />
          </td>
          <td>
            <pre>{{ issue.message }}</pre>
          </td>
        </tr>
      </tbody>

    </table>
    <div class="notification is-info" v-else>Loading check issues...</div>
  </div>
</template>

<style>
.mono{
  font-family: monospace;
}
</style>
