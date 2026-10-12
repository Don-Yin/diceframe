<script setup lang="ts">
defineProps<{ steps: string[]; current: number }>()
</script>

<template>
  <ol class="ruleset-progress" aria-label="角色创建进度">
    <li v-for="(label, index) in steps" :key="label" :class="{ active: current === index + 1, done: current > index + 1 }" :aria-current="current === index + 1 ? 'step' : undefined">
      <span>{{ current > index + 1 ? '✓' : index + 1 }}</span><b>{{ label }}</b>
    </li>
  </ol>
</template>

<style scoped>
.ruleset-progress { display: flex; gap: 8px; padding: 0; margin: 0; list-style: none; overflow-x: auto; }
.ruleset-progress li { display: flex; align-items: center; gap: 7px; min-width: max-content; color: #8793a5; }
.ruleset-progress li::after { content: ''; width: 28px; height: 1px; background: #394455; }
.ruleset-progress li:last-child::after { display: none; }
.ruleset-progress span { display: grid; place-items: center; width: 26px; height: 26px; border: 1px solid #465267; border-radius: 50%; }
.ruleset-progress .active { color: #f0d49a; }
.ruleset-progress .active span, .ruleset-progress .done span { border-color: #b98b43; background: #3d2c16; color: #ffe1a5; }
:global(body.light .ruleset-progress li) { color: #505860; }
:global(body.light .ruleset-progress .active) { color: #79541f; }
:global(body.light .ruleset-progress .active span), :global(body.light .ruleset-progress .done span) { background: #fff0d2; color: #65430e; }
</style>
