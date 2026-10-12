<script setup lang="ts">
/**
 * 二维码取景卡片：扫码登录与邀请/接管链接共用的那一块「给手机看的区域」。
 *
 * 只负责取景与排版——固定尺寸、居中、留白、空态占位——让两处二维码在同一台
 * 手机前是同一个大小和同一套边距。载荷是什么、什么时候过期、下面配什么文案，
 * 都由调用方通过 slot 决定。
 *
 * QrCode 自己硬编码白底（扫码需要的对比度），所以卡片底色只管卡片，不影响取景区。
 */
import { computed } from 'vue'

import QrCode from '@/components/common/QrCode.vue'

const props = withDefaults(defineProps<{
  /** 二维码载荷；为空即空态，渲染 placeholder slot */
  value?: string
  size?: number
}>(), { value: '', size: 196 })

// 取景区尺寸决定卡片高度：空态与有码态高度一致，出码时弹窗不跳动。
const cardStyle = computed(() => ({ minHeight: `${props.size + 56}px` }))
</script>

<template>
  <div class="qr-stage">
    <div class="qr-stage-card" :style="cardStyle">
      <div v-if="value" class="qr-stage-code">
        <QrCode :value="value" :size="size" level="M" />
        <slot name="badge" />
      </div>
      <div v-else class="qr-stage-placeholder">
        <slot name="placeholder" />
      </div>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.qr-stage{display:flex;flex-direction:column;align-items:center;gap:14px;margin:0 0 22px;text-align:center}
.qr-stage-card{display:flex;align-items:center;justify-content:center;width:100%;padding:20px;border:1px solid var(--df-border-soft);border-radius:12px;background:color-mix(in srgb,var(--df-surface-2) 70%,transparent);box-sizing:border-box}
.qr-stage-code{display:flex;flex-direction:column;align-items:center;gap:12px}
.qr-stage-placeholder{display:flex;flex-direction:column;align-items:center;gap:10px;color:var(--df-text-muted)}
.qr-stage-placeholder :deep(p){margin:0;font-size:13px}
</style>
