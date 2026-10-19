<script setup lang="ts">
import {
  TooltipArrow,
  TooltipContent,
  TooltipPortal,
  TooltipProvider,
  TooltipRoot,
  TooltipTrigger,
} from 'reka-ui'

type TooltipSide = 'top' | 'right' | 'bottom' | 'left'
type TooltipAlign = 'start' | 'center' | 'end'

withDefaults(defineProps<{
  content?: string
  side?: TooltipSide
  align?: TooltipAlign
  sideOffset?: number
  delayDuration?: number
  disabled?: boolean
}>(), {
  content: '',
  side: 'top',
  align: 'center',
  sideOffset: 6,
  delayDuration: 300,
  disabled: false,
})
</script>

<template>
  <TooltipProvider :delay-duration="delayDuration">
    <TooltipRoot :disabled="disabled">
      <TooltipTrigger as-child>
        <slot />
      </TooltipTrigger>
      <TooltipPortal>
        <TooltipContent
          class="df-tooltip__content"
          :side="side"
          :align="align"
          :side-offset="sideOffset"
        >
          <slot name="content">{{ content }}</slot>
          <TooltipArrow class="df-tooltip__arrow" />
        </TooltipContent>
      </TooltipPortal>
    </TooltipRoot>
  </TooltipProvider>
</template>

<style scoped>
.df-tooltip__content {
  z-index: 200;
  max-width: min(320px, calc(100vw - 24px));
  padding: 7px 10px;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-sm);
  background: var(--df-surface-raised);
  color: var(--df-text);
  box-shadow: var(--df-shadow);
  font-family: var(--df-font-body);
  font-size: 12px;
  line-height: 1.4;
}
.df-tooltip__arrow { fill: var(--df-surface-raised); }
</style>
