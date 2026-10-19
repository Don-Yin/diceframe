<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import type { ClassValue } from 'clsx'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })
const attrs = useAttrs()
const separatorClass = computed(() => cn('h-px w-full bg-border', attrs.class as ClassValue))
</script>

<template><div v-bind="attrs" data-df-ui="separator" role="separator" :class="separatorClass" /></template>
