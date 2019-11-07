<script>
import Bool from './Bool.vue'
import _ from 'lodash'
import Choice from './Choice.vue'

export default {
  name: 'Task',
  data () {
    return {
      state: 'loading',
      filters: {
        publishable: null,
        analyzer: null,
        path: null
      },
      choices: {
        publishable: [
          {
            name: 'Publishable',
            func: i => i.publishable
          },
          {
            name: 'Non publishable',
            func: i => !i.publishable
          }
        ]
      }
    }
  },
  components: {
    Bool,
    Choice
  },
  mounted () {
    // Update filters from query string
    let publishable = parseInt(this.$route.query.issue)
    this.filters.publishable = isNaN(publishable) ? null : this.choices.publishable[publishable]
    this.filters.path = this.$route.query.path || null
    this.filters.analyzer = this.$route.query.analyzer || null

    // Load report
    var report = this.$store.dispatch('load_report', this.$route.params.taskId)
    report.then(
      (response) => {
        this.$set(this, 'state', 'loaded')
      },
      (error) => {
        this.$set(this, 'state', error.response.status === 404 ? 'missing' : 'error')
      }
    )
  },
  computed: {
    report () {
      return this.$store.state.report
    },
    paths () {
      if (!this.report) {
        return null
      }
      // List sorted unique paths as choices
      return _.sortBy(_.uniq(_.map(this.report.issues, 'path')))
    },
    analyzers () {
      if (!this.report) {
        return null
      }
      // List sorted unique analyzers as choices
      return _.sortBy(_.uniq(_.map(this.report.issues, 'analyzer')))
    },
    nb_publishable () {
      if (!this.report || !this.report.issues) {
        return 0
      }
      return this.report.issues.filter(i => i.publishable).length
    },
    issues () {
      let issues = this.report ? this.report.issues : []

      // Filter by publishable
      if (this.filters.publishable !== null) {
        issues = _.filter(issues, this.filters.publishable.func)
      }

      // Filter by path
      if (this.filters.path !== null) {
        issues = _.filter(issues, i => i.path === this.filters.path)
      }

      // Filter by analyzer
      if (this.filters.analyzer !== null) {
        issues = _.filter(issues, i => i.analyzer === this.filters.analyzer)
      }

      // Always display publishable first
      return _.sortBy(issues, i => !i.publishable)
    }
  },
  filters: {
    from_timestamp (value) {
      return new Date(value * 1000).toUTCString()
    }
  }
}
</script>

<template>
  <div>
    <h1 class="title">Task <a :href="'https://firefox-ci-tc.services.mozilla.com/tasks/' + $route.params.taskId" target="_blank">{{ $route.params.taskId }}</a></h1>

    <div class="notification is-info" v-if="state == 'loading'">Loading report...</div>
    <div class="notification is-warning" v-else-if="state == 'missing'">No report, so no issues !</div>
    <div class="notification is-danger" v-else-if="state == 'error'">Failure</div>
    <div v-else-if="state == 'loaded'">

      <nav class="level" v-if="report">
        <div class="level-item has-text-centered">
          <div>
            <p class="heading">Publishable</p>
            <p class="title">{{ nb_publishable }}</p>
          </div>
        </div>
        <div class="level-item has-text-centered">
          <div>
            <p class="heading">Issues</p>
            <p class="title">{{ report.issues.length }}</p>
          </div>
        </div>
        <div class="level-item has-text-centered">
          <div>
            <p class="heading">Source</p>
            <p class="title"><a :href="report.revision.url" target="_blank">{{ report.revision.title }}</a></p>
          </div>
        </div>
        <div class="level-item has-text-centered">
          <div>
            <p class="heading">Reported</p>
            <p class="title">{{ report.time|from_timestamp }}</p>
          </div>
        </div>
      </nav>

      <table class="table is-fullwidth" v-if="issues">
        <thead>
          <tr>
            <td><Choice :choices="analyzers" name="analyzer" v-on:new-choice="filters.analyzer = $event"/></td>
            <td><Choice :choices="paths" name="path" v-on:new-choice="filters.path = $event"/></td>
            <td>Lines</td>
            <td><Choice :choices="choices.publishable" name="issue" v-on:new-choice="filters.publishable = $event"/></td>
            <td>Check</td>
            <td>Level</td>
            <td>Message</td>
          </tr>
        </thead>

        <tbody>
          <tr v-for="issue in issues" :class="{'publishable': issue.publishable}">
            <td>
              <span v-if="issue.analyzer == 'mozlint'">{{ issue.linter }}<br />by Mozlint</span>
              <span v-else>{{ issue.analyzer }}</span>
            </td>
            <td class="path">{{ issue.path }}</td>
            <td>{{ issue.line }} <span v-if="issue.nb_lines > 1">&rarr; {{ issue.line - 1 + issue.nb_lines }}</span></td>
            <td>
              <Bool :value="issue.publishable" name="Publishable" />
              <ul>
                <li><Bool :value="issue.in_patch" name="In patch" /></li>
                <li><Bool :value="issue.validates" name="Validated" /></li>
                <li><Bool :value="issue.publishable" name="New issue" /></li>
              </ul>
            </td>

            <td>
              <span v-if="issue.analyzer == 'mozlint'">{{ issue.rule }}</span>
              <span v-if="issue.analyzer == 'clang-tidy'">{{ issue.check }}</span>
              <span v-if="issue.analyzer == 'clang-format'">Style issue</span>
              <span v-if="issue.analyzer == 'infer'">{{ issue.bug_type }}</span>
              <span v-if="issue.analyzer == 'Coverity'">{{ issue.bug_type }}<br /><code>{{ issue.kind }}</code></span>
            </td>
            <td>
              <span v-if="issue.level == 'error' || issue.type == 'error' || issue.kind == 'ERROR' || issue.analyzer == 'Coverity'" class="tag is-danger">Error</span>
              <span v-if="issue.level == 'warning' || issue.type == 'warning' || issue.kind == 'WARNING' || issue.analyzer == 'clang-format'" class="tag is-warning">Warning</span>
            </td>
            <td>
              <pre v-if="issue.analyzer == 'Coverity'">{{ issue.message }}</pre>
              <p v-else>{{ issue.message }}</p>

              <pre v-if="issue.body">
                {{ issue.body }}
              </pre>

              <div v-if="issue.analyzer == 'clang-format' && issue.mode == 'replace'">
                <strong>Replace</strong>
                <pre>{{ issue.old_lines }}</pre>
                <strong>by these:</strong>
                <pre>{{ issue.new_lines }}</pre>
              </div>
              <div v-if="issue.analyzer == 'clang-format' && issue.mode == 'insert'">
                <strong>Insert these lines</strong>
                <pre>{{ issue.new_lines }}</pre>
              </div>
              <div v-if="issue.analyzer == 'clang-format' && issue.mode == 'delete'">
                <strong>Delete these lines</strong>
                <pre>{{ issue.old_lines }}</pre>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="notification is-info" v-else>No issues !</div>
  </div>
</template>

<style scoped>
tr.publishable {
  background: #e6ffcc;
}

td.path {
  color: #4d4d4d;
  font-family: monospace;
}
</style>
