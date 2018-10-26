<script>
import mixins from './mixins.js'

export default {
  mixins: [
    mixins.stats,
    mixins.date
  ],
  props: {
    name: String
  }
}
</script>

</script>

<template>
  <div>
    <h1 class="title">{{ name }}</h1>
    <h2 class="subtitle" v-if="stats && stats.ids">
      <span>
        Loaded {{ stats.loaded }}
        <span v-if="stats.errors > 0" class="has-text-danger" :title="stats.errors + ' errors while loading reports'"> + {{ stats.errors }}</span>
        / {{ stats.ids.length }} tasks with issues
      </span>
      <span v-if="stats && stats.start_date" :title="stats.start_date">, since {{ stats.start_date|since }} ago</span>
    </h2>

    <div v-if="stats">
      <progress class="progress is-info" :class="{'is-info': progress < 100, 'is-success': progress >= 100}" :value="progress" max="100">{{ progress }}%</progress>
    </div>
  </div>
</template>
