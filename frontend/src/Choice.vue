<template>
  <div class="dropdown is-hoverable">
    <div class="dropdown-trigger">
      <button class="button" aria-haspopup="true" aria-controls="dropdown-menu">
        <span v-if="current === null">{{ default_choice_name }}</span>
        <span v-else>{{ current|name }}</span>
      </button>
    </div>
    <div class="dropdown-menu" id="dropdown-menu" role="menu">
      <div class="dropdown-content">
        <a class="dropdown-item" v-on:click="select(null, $event)" :class="{'is-active': current === null }">
          {{ default_choice_name }}
        </a>
        <hr class="dropdown-divider">
        <a class="dropdown-item" v-for="choice in choices" v-on:click="select(choice, $event)" :class="{'is-active': current === choice }">
          {{ choice|name }}
        </a>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  props: {
    'name': String,
    'choices': Array
  },
  data: function () {
    return {
      current: null
    }
  },
  mounted: function () {
    let initial = this.$route.query[this.name]
    if (initial && this.choices) {
      this.current = isNaN(parseInt(initial)) ? initial : this.choices[initial]
    }
  },
  methods: {
    select: function (choice, evt) {
      evt.stopPropagation()

      // Save new choice
      this.current = choice
      this.$emit('new-choice', choice)

      // Set value in the url for sharing
      var query = Object.assign({}, this.$route.query)
      if (choice !== null) {
        query[this.name] = typeof choice === 'string' ? choice : this.choices.indexOf(choice)
      } else if (this.name in query) {
        delete query[this.name]
      }
      this.$router.push({ 'query': query })
    }
  },
  computed: {
    default_choice_name: function () {
      return 'All ' + this.name + 's'
    }
  },
  filters: {
    name: function (choice) {
      return typeof choice === 'string' ? choice : choice.name
    }
  }
}
</script>
