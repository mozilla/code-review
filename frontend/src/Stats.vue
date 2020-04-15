<script>
import mixins from './mixins.js'
import Progress from './Progress.vue'
import Choice from './Choice.vue'
import Chartist from 'chartist'

export default {
  mixins: [
    mixins.stats,
    mixins.date
  ],
  data () {
    // Set default to since one month back
    let since = new Date()
    since.setMonth(since.getMonth() - 1)
    since = since.toISOString().substring(0, 10)

    return {
      // Data filters
      since: since,
      analyzer: null,
      repository: null,
      check: null,

      // Sort by a column
      sortColumn: 'total',

      // Options for chartist
      chartOptions: {
        height: 300,
        axisX: {
          type: Chartist.FixedScaleAxis,
          divisor: 15,
          labelInterpolationFnc: function (value) {
            const date = new Date(value)
            return `${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}`
          }
        }
      }
    }
  },
  components: { Progress, Choice },
  mounted () {
    this.load()
  },
  methods: {
    load (reset) {
      let payload = {}
      if (reset === true) {
        this.set(this, 'since', null)
      } else {
        payload.since = this.since
      }

      // Stats since provided date
      this.$store.dispatch('load_stats', payload)

      // History since provided date
      this.$store.dispatch('load_history', payload)
    },
    use_filter (name, value) {
      // Store new filter value
      this.$set(this, name, value)

      // Load new history data
      this.$store.dispatch('load_history', {
        repository: this.repository,
        analyzer: this.analyzer,
        check: this.check,
        since: this.since
      })
    },
    sort_by (column) {
      // Store new sort column
      this.$set(this, 'sortColumn', column)
    }
  },
  computed: {
    stats_filtered () {
      if (!this.stats) {
        return null
      }

      // Sort by specified column
      let stats = this.stats.sort((x, y) => x[this.sortColumn] < y[this.sortColumn])

      // Apply filters
      if (this.repository !== null) {
        stats = stats.filter(s => s.repository === this.repository)
      }
      if (this.analyzer !== null) {
        stats = stats.filter(s => s.analyzer === this.analyzer)
      }
      if (this.check !== null) {
        stats = stats.filter(s => s.check === this.check)
      }

      return stats
    },

    // Available filtering data
    repositories () {
      return [...new Set(this.stats_filtered.map(x => x.repository))].sort()
    },
    analyzers () {
      return [...new Set(this.stats_filtered.map(x => x.analyzer))].sort()
    },
    checks () {
      return [...new Set(this.stats_filtered.map(x => x.check))].sort()
    },

    history () {
      const history = this.$store.state.history
      if (!history) {
        return null
      }

      return {
        series: [
          {
            name: 'Total issues',
            data: history.map(point => { return { x: new Date(point.date), y: point.total } })
          }
        ]
      }
    }
  }
}
</script>

<template>
  <div>
    <div class="field">
      <label class="label">Issues since:</label>
      <div class="control">
        <input class="input" type="date" v-model="since" v-on:change="load()" />
        <button class="button" v-on:click="load(true)">Since beginning</button>
      </div>
    </div>

    <Progress name="Statistics" />

    <chartist v-if="history !== null"
        type="Line"
        :data="history"
        :options="chartOptions" >
    </chartist>

    <div v-if="stats">
      <table class="table is-fullwidth" v-if="stats">
        <thead>
          <tr>
            <th>
              <Choice :choices="repositories" name="repository" v-on:new-choice="use_filter('repository', $event)"/>
            </th>
            <th>
              <Choice :choices="analyzers" name="analyzer" v-on:new-choice="use_filter('analyzer', $event)"/>
            </th>
            <th>
              <Choice :choices="checks" name="check" v-on:new-choice="use_filter('check', $event)"/>
            </th>
            <th>
              <button class="button is-info" v-on:click="sort_by('total')" :disabled="sortColumn == 'total'">Detected</button>
            </th>
            <th>
              <button class="button is-info" v-on:click="sort_by('publishable')" :disabled="sortColumn == 'publishable'">Publishable</button>
            </th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="stat in stats_filtered" :class="{'publishable': stat.publishable > 0}">
            <td>{{ stat.repository }}</td>
            <td>{{ stat.analyzer }}</td>
            <td>{{ stat.check }}</td>
            <td>{{ stat.total }}</td>
            <td>
              <strong v-if="stat.publishable > 0">{{ stat.publishable }}</strong>
              <span class="has-text-grey" v-else>0</span>
            </td>
            <td>
              <router-link class="button is-small" :to="{ name: 'check', params: { repository: stat.repository, analyzer: stat.analyzer, check: stat.check }}">View issues</router-link>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="notification is-info" v-else>Loading tasks...</div>

  </div>
</template>

<style scoped>
tr.publishable {
  background: #e6ffcc;
}

.ct-square {
  margin: 20px 0;
  height: 300px;
}
</style>
