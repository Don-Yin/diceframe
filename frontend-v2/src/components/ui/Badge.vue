<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { cva, type VariantProps } from 'class-variance-authority'
import type { ClassValue } from 'clsx'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const badgeVariants = cva(
  'inline-flex items-center rounded-sm border px-2 py-1 text-[11px] font-semibold leading-none',
  {
    variants: {
      variant: {
        default: 'border-border bg-muted text-muted-foreground',
        accent: 'border-accent/50 bg-accent/10 text-accent-foreground',
        success: 'border-success/50 bg-success/15 text-success',
        warning: 'border-warning/50 bg-warning/15 text-warning',
        danger: 'border-destructive/50 bg-destructive/15 text-destructive-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

const props = withDefaults(defineProps<{ variant?: VariantProps<typeof badgeVariants>['variant'] }>(), { variant: 'default' })
const attrs = useAttrs()
const badgeClass = computed(() => cn(badgeVariants({ variant: props.variant }), attrs.class as ClassValue))
</script>

<template><span v-bind="attrs" data-df-ui="badge" :class="badgeClass"><slot /></span></template>
