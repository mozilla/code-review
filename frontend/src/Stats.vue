<script>
import mixins from "./mixins.js";
import Progress from "./Progress.vue";
import Choice from "./Choice.vue";
import {
  Chart as ChartJS,
  Title,
  Tooltip,
  Legend,
  LineElement,
  LinearScale,
  CategoryScale,
  PointElement,
} from "chart.js";
import { Line } from "vue-chartjs";

ChartJS.register(
  Title,
  Tooltip,
  Legend,
  LineElement,
  LinearScale,
  CategoryScale,
  PointElement
);

export default {
  mixins: [mixins.stats, mixins.date],
  data() {
    // Set default to since one month back
    let dateSince = new Date();
    dateSince.setMonth(dateSince.getMonth() - 1);
    dateSince = dateSince.toISOString().substring(0, 10);

    return {
      // Data filters
      dateSince,
      analyzer: null,
      repository: null,
      check: null,

      // Sort by a column
      sortColumn: "total",

      // Options for Line chart
      chartOptions: {
        axisX: {
          type: ChartJS.FixedScaleAxis,
          divisor: 15,
          labelInterpolationFnc: function (value) {
            const date = new Date(value);
            return `${date.getDate()}/${
              date.getMonth() + 1
            }/${date.getFullYear()}`;
          },
        },
      },
    };
  },
  components: { Progress, Choice, Line },
  mounted() {
    this.load();
  },
  methods: {
    load(reset) {
      const payload = {};
      if (reset === true || this.dateSince === "") {
        payload.since = null;
      } else {
        payload.since = this.dateSince;
      }

      // Stats since provided date
      this.$store.dispatch("load_stats", payload);

      // History since provided date
      this.$store.dispatch("load_history", payload);
    },
    use_filter(name, value) {
      // Store new filter value
      this[name] = value;

      // Load new history data
      this.$store.dispatch("load_history", {
        repository: this.repository,
        analyzer: this.analyzer,
        check: this.check,
        since: this.dateSince,
      });
    },
    sort_by(column) {
      // Store new sort column
      this.sortColumn = column;
    },
  },
  computed: {
    stats_filtered() {
      if (!this.stats) {
        return null;
      }

      // Sort by specified column
      let stats = this.stats.sort(
        (x, y) => x[this.sortColumn] < y[this.sortColumn]
      );

      // Apply filters
      if (this.repository !== null) {
        stats = stats.filter((s) => s.repository === this.repository);
      }
      if (this.analyzer !== null) {
        stats = stats.filter((s) => s.analyzer === this.analyzer);
      }
      if (this.check !== null) {
        stats = stats.filter((s) => s.check === this.check);
      }

      return stats;
    },

    // Available filtering data
    repositories() {
      return [...new Set(this.stats_filtered.map((x) => x.repository))].sort();
    },
    analyzers() {
      return [...new Set(this.stats_filtered.map((x) => x.analyzer))].sort();
    },
    checks() {
      return [...new Set(this.stats_filtered.map((x) => x.check))].sort();
    },

    history() {
      const history = this.$store.state.history;
      if (!history) {
        return null;
      }

      const labels = history.flatMap((point) => point.date);
      const data = history.flatMap((point) => point.total);

      return {
        labels: labels,
        datasets: [
          {
            borderColor: "rgb(75, 192, 192)",
            pointBorderColor: "rgb(75, 192, 192)",
            pointBackgroundColor: "rgb(75, 192, 192)",
            tension: 0.1,
            label: "Total issues",
            data: data,
          },
        ],
      };
    },
  },
};
</script>

<template>
  <div>
    <Progress name="Statistics" />

    <div>
      <label>Issues created since:</label>
      <div class="field has-addons">
        <div class="control">
          <input
            class="input"
            type="date"
            v-model="dateSince"
            v-on:change="load()"
          />
        </div>
        <div class="control">
          <button class="button is-info" v-on:click="load(true)">
            Beginning
          </button>
        </div>
      </div>
    </div>

    <Line
      v-if="history"
      :data="history"
      :options="chartOptions"
      :height="100"
    ></Line>

    <div v-if="stats">
      <table class="table is-fullwidth" v-if="stats">
        <thead>
          <tr>
            <th>
              <Choice
                :choices="repositories"
                name="repository"
                v-on:new-choice="use_filter('repository', $event)"
              />
            </th>
            <th>
              <Choice
                :choices="analyzers"
                name="analyzer"
                v-on:new-choice="use_filter('analyzer', $event)"
              />
            </th>
            <th>
              <Choice
                :choices="checks"
                name="check"
                v-on:new-choice="use_filter('check', $event)"
              />
            </th>
            <th>
              <button
                class="button is-info"
                v-on:click="sort_by('total')"
                :disabled="sortColumn == 'total'"
              >
                Detected
              </button>
            </th>
            <th>
              <button
                class="button is-info"
                v-on:click="sort_by('publishable')"
                :disabled="sortColumn == 'publishable'"
              >
                Publishable
              </button>
            </th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="stat in stats_filtered"
            :class="{ publishable: stat.publishable > 0 }"
          >
            <td>{{ stat.repository }}</td>
            <td>{{ stat.analyzer }}</td>
            <td>{{ stat.check }}</td>
            <td>{{ stat.total }}</td>
            <td>
              <strong v-if="stat.publishable > 0">{{
                stat.publishable
              }}</strong>
              <span class="has-text-grey" v-else>0</span>
            </td>
            <td>
              <router-link
                class="button is-small"
                :to="{
                  name: 'check',
                  params: {
                    repository: stat.repository,
                    analyzer: stat.analyzer,
                    check: stat.check,
                  },
                }"
                >View issues</router-link
              >
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
