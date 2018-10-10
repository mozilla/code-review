<template>
  <div class="dropdown is-hoverable">
    <div class="dropdown-trigger">
      <button class="button" aria-haspopup="true" aria-controls="dropdown-menu">
        <span v-if="current === null">{{ default_choice_name }}</span>
        <span v-else>{{ current.name }}</span>
      </button>
    </div>
    <div class="dropdown-menu" id="dropdown-menu" role="menu">
      <div class="dropdown-content">
        <a href="#" class="dropdown-item" v-on:click="select(null)" :class="{'is-active': current === null }">
          {{ default_choice_name }}
        </a>
        <hr class="dropdown-divider">
        <a href="#" class="dropdown-item" v-for="choice in choices" v-on:click="select(choice)" :class="{'is-active': current === choice }">
          {{ choice.name }}
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
  methods: {
    select: function (choice) {
      this.current = choice
      this.$emit('new-choice', choice)
    }
  },
  computed: {
    default_choice_name: function () {
      return 'All ' + this.name + 's'
    }
  }
}
</script>
