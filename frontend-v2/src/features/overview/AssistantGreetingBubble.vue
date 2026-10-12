<script setup lang="ts">
import { ref } from 'vue'
import { useLocale } from '@/composables/useLocale'

const emit = defineEmits<{ open: [] }>()
const { t } = useLocale()

const BUBBLE_DISMISSED_KEY = 'overview_assistant_bubble_dismissed'

// storage 被禁用/策略限制时安全降级：当前 session 仍关闭，刷新后允许再次出现。
function readDismissed(): boolean {
  try {
    return localStorage.getItem(BUBBLE_DISMISSED_KEY) === '1'
  } catch {
    return false
  }
}

function persistDismissed() {
  try {
    localStorage.setItem(BUBBLE_DISMISSED_KEY, '1')
  } catch {
    // 写不进去就不持久化，不影响本 session 的关闭行为
  }
}

const visible = ref(!readDismissed())

function dismiss() {
  visible.value = false
  persistDismissed()
}

function chooseOpen() {
  dismiss()
  emit('open')
}
</script>

<template>
  <div v-if="visible" class="overview-assistant-bubble-wrap">
    <button type="button" class="overview-assistant-bubble" @click="chooseOpen">{{ t('assistantBubbleText') }}</button>
    <button type="button" class="overview-assistant-bubble-close" :aria-label="t('close')" @click="dismiss">×</button>
  </div>
</template>

<style scoped>
/* 助手引导气泡：贴在悬浮圆钮左侧、垂直居中，不占上方空间。
   点气泡进入助手，× 关闭后不再出现。 */
.overview-assistant-bubble-wrap {
  position: fixed;
  right: calc(18px + 48px + 10px);
  bottom: calc(30px + env(safe-area-inset-bottom));
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 9px 10px 9px 13px;
  border: 1px solid color-mix(in srgb, var(--df-accent-strong) 45%, var(--df-border-soft));
  border-radius: 12px;
  background: linear-gradient(180deg, var(--df-surface-raised), var(--df-surface-2));
  color: var(--df-text);
  box-shadow: var(--df-shadow);
  animation: assistant-bubble-in .18s ease-out;
}

.overview-assistant-bubble {
  border: 0;
  padding: 0;
  background: none;
  color: var(--df-text);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}

.overview-assistant-bubble:hover {
  color: var(--df-interactive-strong);
}

.overview-assistant-bubble-close {
  border: 0;
  padding: 0 2px;
  background: none;
  color: var(--df-text-muted);
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
}

.overview-assistant-bubble-close:hover {
  color: var(--df-text);
}

@keyframes assistant-bubble-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}

@media (max-width: 700px) {
  .overview-assistant-bubble-wrap {
    right: calc(14px + 44px + 8px);
    bottom: calc(76px + env(safe-area-inset-bottom));
    max-width: calc(100vw - 28px);
  }
}
</style>
