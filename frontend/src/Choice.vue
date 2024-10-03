<template>
  <div class="dropdown is-hoverable">
    <div class="dropdown-trigger">
      <button class="button" aria-haspopup="true" aria-controls="dropdown-menu">
        <span v-if="current === null">{{ default_choice_name }}</span>
        <span v-else>{{ displayName(current) }}</span>
      </button>
    </div>
    <div class="dropdown-menu" id="dropdown-menu" role="menu">
      <div class="dropdown-content">
        <a
          class="dropdown-item"
          v-on:click="select(null, $event)"
          :class="{ 'is-active': current === null }"
        >
          No filter
        </a>
        <hr class="dropdown-divider" />
        <a
          class="dropdown-item"
          v-for="choice in choices"
          v-on:click="select(choice, $event)"
          :class="{
            'is-active': current === choice || current === choice.value,
          }"
        >
          {{ displayName(choice) }}
        </a>
      </div>
    </div>
  </div>
</template>

<script>
import mixins from "./mixins.js";

export default {
  props: {
    name: String,
    choices: Array,
  },
  mixins: [mixins.query],
  data: () => ({
    choice: undefined,
  }),
  methods: {
    select: function (choice, evt) {
      evt.stopPropagation();

      // Save new choice
      this.choice = choice;
      this.$emit("new-choice", choice);
    },
    displayName(choice) {
      return typeof choice === "string" ? choice : choice.slug || choice.name;
    },
  },
  computed: {
    current() {
      let current = null;
      const choice = this.choice || this.$route.query[this.name];
      if (choice && this.choices) {
        current = this.choices.find((c) => c === choice || c.value === choice);
        if (!current) {
          current = isNaN(parseInt(choice)) ? choice : this.choices[choice];
        }
      }
      return current;
    },
    default_choice_name: function () {
      return "Filter by " + this.name;
    },
  },
};
</script>
