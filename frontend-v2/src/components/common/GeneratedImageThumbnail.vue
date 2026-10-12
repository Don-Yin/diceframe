<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { generatedImageUrl } from '@/api/generatedImages'
import ImageLightbox from '@/components/common/ImageLightbox.vue'

const props = withDefaults(defineProps<{ assetId?: string; gameKey?: string; alt?: string; size?: number }>(), { size: 72 })
const url = ref('')
const failed = ref(false)
const lightboxOpen = ref(false)
let loadVersion = 0

function clearUrl() {
  if (url.value.startsWith('blob:')) URL.revokeObjectURL(url.value)
  url.value = ''
}

watch(
  () => [props.assetId || '', props.gameKey || ''] as const,
  async ([assetId, gameKey]) => {
    const version = ++loadVersion
    clearUrl()
    failed.value = false
    if (!assetId) return
    let nextUrl = ''
    try {
      nextUrl = await generatedImageUrl(assetId, gameKey)
      if (version !== loadVersion) {
        URL.revokeObjectURL(nextUrl)
        return
      }
      url.value = nextUrl
    } catch {
      if (nextUrl.startsWith('blob:')) URL.revokeObjectURL(nextUrl)
      if (version === loadVersion) failed.value = true
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  loadVersion += 1
  clearUrl()
})
</script>

<template>
  <span class="generated-image-thumbnail" :style="{ width: `${size}px`, height: `${size}px` }">
    <img v-if="url" :src="url" :alt="alt || ''" role="button" tabindex="0" @click.stop="lightboxOpen = true" @keydown.enter.stop="lightboxOpen = true">
    <span v-else>{{ failed ? '×' : '…' }}</span>
  </span>
  <ImageLightbox :open="lightboxOpen" :src="url" :alt="alt" @close="lightboxOpen = false" />
</template>

<style scoped>
.generated-image-thumbnail{display:inline-grid;place-items:center;overflow:hidden;flex:0 0 auto;border-radius:8px;border:1px solid var(--df-border,rgba(128,128,128,.3));background:var(--df-bg-soft,rgba(0,0,0,.12))}
.generated-image-thumbnail img{width:100%;height:100%;object-fit:cover;cursor:zoom-in}
</style>
