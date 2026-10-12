<script setup lang="ts">
/**
 * 「对方要连的地址」选择器。
 *
 * 扫码登录和邀请/接管链接问的是同一个问题——从服务端给出的候选里挑一个对方真正
 * 能访问到的地址——所以标题、刷新、下拉、说明这套结构放在一个组件里，两个弹窗
 * 不再各自长一套排版出来。
 *
 * 候选从哪来是调用方的事（见 composables/useReachableAddresses）；本组件只出示
 * 与选择，不发请求。
 */
import { NIcon, NSelect } from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'

import { useLocale } from '@/composables/useLocale'

withDefaults(defineProps<{
  value: string
  options: { label: string; value: string }[]
  label: string
  hint?: string
  placeholder?: string
  /** 下拉自身的加载态 */
  loading?: boolean
  /** 刷新图标的转动态：调用方可能同时在拉别的东西（例如设备清单） */
  busy?: boolean
}>(), { loading: false, busy: false })

const emit = defineEmits<{ 'update:value': [string]; refresh: [] }>()
const { t } = useLocale()
</script>

<template>
  <div class="address-picker">
    <div class="address-picker-head">
      <label>{{ label }}</label>
      <button
        type="button"
        class="address-picker-refresh"
        :class="{ 'is-loading': busy || loading }"
        :title="t('refresh')"
        :aria-label="t('refresh')"
        @click="emit('refresh')"
      >
        <NIcon :component="RefreshOutline" />
      </button>
    </div>
    <NSelect
      :value="value"
      :options="options"
      :loading="loading"
      :placeholder="placeholder"
      @update:value="emit('update:value', $event)"
    />
    <!-- 说明可以是纯文案，也可以是带链接/警告的一组段落（邀请链接就是后者）。 -->
    <div v-if="hint || $slots.hint" class="muted address-picker-hint">
      <slot name="hint">{{ hint }}</slot>
    </div>
  </div>
</template>

<style scoped>
.address-picker{margin:0 0 20px}
.address-picker-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
.address-picker-head label{font-size:13px;font-weight:700;color:var(--df-text-secondary)}
.address-picker-refresh{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;padding:0;border:1px solid var(--df-border-soft);border-radius:6px;background:transparent;color:var(--df-text-muted);cursor:pointer;flex:0 0 auto}
.address-picker-refresh:hover{color:var(--df-accent-strong);border-color:var(--df-border)}
.address-picker-refresh.is-loading :deep(svg){animation:address-picker-spin .8s linear infinite}
@keyframes address-picker-spin{to{transform:rotate(360deg)}}
.address-picker-hint{display:flex;flex-direction:column;gap:6px;margin:6px 0 0;font-size:12px;line-height:1.6}
.address-picker-hint :deep(p){margin:0}
</style>
