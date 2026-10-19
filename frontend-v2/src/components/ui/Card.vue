<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import type { ClassValue } from 'clsx'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{ as?: 'article' | 'section' | 'div' }>(), { as: 'section' })
const attrs = useAttrs()
const cardClass = computed(() => cn(
  'rounded-lg border border-border bg-card text-card-foreground shadow-[var(--df-shadow)]',
  attrs.class as ClassValue,
))
</script>

<template>
  <component :is="props.as" v-bind="attrs" data-df-ui="card" :class="cardClass"><slot /></component>
</template>
