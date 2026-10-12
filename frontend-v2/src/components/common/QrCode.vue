<script setup lang="ts">
/**
 * 二维码渲染：把一段文本画成 SVG。
 *
 * 用 SVG 而不是 canvas / img：手机对着屏幕扫，缩放到任意尺寸都要保持边缘锐利，
 * 并且深浅主题下前景色要跟着主题令牌走。
 *
 * 取景区必须是纯白底 + 足够的 quiet zone（四周留白 4 个模块是规范要求），
 * 否则暗色主题下对比度不足，多数手机扫不出来——所以这里的白底是刻意硬编码的，
 * 不跟随主题。
 */
import { computed } from 'vue'
import qrcode from 'qrcode-generator'

const props = withDefaults(defineProps<{
  value: string
  /** 渲染像素尺寸（正方形边长） */
  size?: number
  /** 容错级别；带 logo 或反光屏幕建议用 'M' 以上 */
  level?: 'L' | 'M' | 'Q' | 'H'
}>(), { size: 200, level: 'M' })

const QUIET_ZONE = 4

/**
 * 把文本按 UTF-8 编码成字节，供 qrcode 使用。
 *
 * qrcode-generator v2 的 **ESM 构建不再提供 `stringToBytesFuncs`**（只有 CJS 构建
 * `dist/qrcode.js` 有），而 Vite 在 dev 与 build 都按 `exports.import` 解析到
 * `dist/qrcode.mjs`。该包同时只有一个主入口的 exports 映射，拿不到它自带的
 * `qrcode_UTF8` 子模块（`exports` 里没有子路径）。
 *
 * 直接写 `qrcode.stringToBytesFuncs['UTF-8']` 会在 ESM 下抛 TypeError，并且因为它
 * 发生在 computed 里，整个二维码会静默不渲染。类型定义（v1 风格 `export =` 的
 * .d.ts）仍然声明了 `stringToBytesFuncs`，所以 typecheck 也发现不了。
 *
 * 因此：包自带表存在时优先用它；否则用标准 `TextEncoder`（所有目标浏览器与 jsdom
 * 都有），保留"非 ASCII 不被编坏"的原始意图。
 */
function utf8StringToBytes(factory: typeof qrcode): (text: string) => number[] {
  const fromPackage = factory.stringToBytesFuncs?.['UTF-8']
  if (typeof fromPackage === 'function') return fromPackage
  return (text: string) => Array.from(new TextEncoder().encode(text))
}

const model = computed(() => {
  if (!props.value) return null
  qrcode.stringToBytes = utf8StringToBytes(qrcode)
  const qr = qrcode(0, props.level)
  qr.addData(props.value)
  qr.make()
  const count = qr.getModuleCount()
  const parts: string[] = []
  for (let row = 0; row < count; row++) {
    for (let col = 0; col < count; col++) {
      // 逐块 rect 合并成单条 path：模块数多时比几百个 <rect> 节点便宜得多。
      if (qr.isDark(row, col)) parts.push(`M${col + QUIET_ZONE} ${row + QUIET_ZONE}h1v1h-1z`)
    }
  }
  return { extent: count + QUIET_ZONE * 2, path: parts.join('') }
})
</script>

<template>
  <svg
    v-if="model"
    class="qr-code"
    :width="size"
    :height="size"
    :viewBox="`0 0 ${model.extent} ${model.extent}`"
    role="img"
    shape-rendering="crispEdges"
  >
    <rect :width="model.extent" :height="model.extent" fill="#ffffff" />
    <path :d="model.path" fill="#000000" />
  </svg>
</template>

<style scoped>
.qr-code{display:block;border-radius:8px}
</style>
