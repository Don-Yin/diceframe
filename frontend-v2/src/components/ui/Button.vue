<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { cva, type VariantProps } from 'class-variance-authority'
import type { ClassValue } from 'clsx'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const buttonVariants = cva(
  'inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-md border text-sm font-semibold leading-none transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'border-border bg-secondary text-secondary-foreground hover:bg-muted',
        primary: 'border-primary/70 bg-primary text-primary-foreground hover:bg-primary/90',
        success: 'border-success/70 bg-success text-primary-foreground hover:bg-success/90',
        danger: 'border-destructive/70 bg-destructive text-destructive-foreground hover:bg-destructive/90',
        ghost: 'border-transparent bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground',
        outline: 'border-border bg-transparent text-foreground hover:border-accent hover:bg-accent/10',
      },
      size: {
        sm: 'min-h-8 px-3 text-xs',
        md: 'min-h-9 px-4',
        lg: 'min-h-11 px-5 text-base',
        icon: 'size-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'md' },
  },
)

type ButtonVariants = VariantProps<typeof buttonVariants>

const props = withDefaults(defineProps<{
  variant?: ButtonVariants['variant']
  size?: ButtonVariants['size']
  type?: 'button' | 'submit' | 'reset'
}>(), {
  type: 'button',
  variant: 'default',
  size: 'md',
})

const attrs = useAttrs()
const buttonClass = computed(() => cn(buttonVariants({ variant: props.variant, size: props.size }), attrs.class as ClassValue))
</script>

<template>
  <button
    v-bind="attrs"
    data-df-ui="button"
    :type="props.type"
    :class="buttonClass"
  >
    <slot />
  </button>
</template>
