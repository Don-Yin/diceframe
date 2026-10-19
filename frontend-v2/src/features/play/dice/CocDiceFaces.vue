<script setup lang="ts">
import { computed } from 'vue'
import type { PercentileDice } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import { cocCopy } from './cocCopy'
import { validPercentileDice } from './presentation'

const props = defineProps<{ dice: PercentileDice }>()
const { locale } = useLocale()
const copy = computed(() => cocCopy[locale.value])
const valid = computed(() => validPercentileDice(props.dice))
</script>

<template>
  <div v-if="valid" class="coc-dice-faces" data-testid="coc-dice-faces">
    <p>{{ copy.units }}: <b>{{ dice.units }}</b></p>
    <p>{{ copy.bonus }}: {{ dice.bonus_dice }} · {{ copy.penalty }}: {{ dice.penalty_dice }}</p>
    <div class="coc-combinations" :aria-label="copy.tens">
      <span v-for="(ten, index) in dice.tens" :key="index" class="coc-combination" :class="{ taken: index === dice.taken_index }" :data-testid="index === dice.taken_index ? 'coc-dice-taken' : undefined">
        {{ String(ten).padStart(2, '0') }} + {{ dice.units }} = {{ dice.candidates[index] }}
        <small v-if="index === dice.taken_index">{{ copy.taken }}</small>
      </span>
    </div>
  </div>
</template>

<style scoped>
.coc-dice-faces { margin:.5rem 0; }
.coc-dice-faces p { margin:.3rem 0; }
.coc-combinations { display:flex; flex-wrap:wrap; gap:.5rem; }
.coc-combination { padding:.4rem .6rem; border:1px solid var(--border-color, #8885); border-radius:.4rem; }
.coc-combination.taken { border-color:var(--df-success); background:color-mix(in srgb, var(--df-success) 12%, transparent); }
.coc-combination small { margin-left:.5rem; }
</style>
