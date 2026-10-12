<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { generatedImageUrl } from '@/api/generatedImages'
import ImageLightbox from '@/components/common/ImageLightbox.vue'

const props = defineProps<{ assetId: string; gameKey?: string; alt?: string }>()
const url = ref('')
const lightboxOpen = ref(false)
let loadVersion = 0

function clearUrl() {
  if (url.value.startsWith('blob:')) URL.revokeObjectURL(url.value)
  url.value = ''
}

watch(
  () => [props.assetId, props.gameKey || ''] as const,
  async ([assetId, gameKey]) => {
    const version = ++loadVersion
    clearUrl()
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
  <figure v-if="url" class="scene-image-block" data-testid="scene-image">
    <img :src="url" :alt="alt || ''" loading="lazy" role="button" tabindex="0" @click="lightboxOpen = true" @keydown.enter="lightboxOpen = true" />
  </figure>
  <ImageLightbox :open="lightboxOpen" :src="url" :alt="alt" @close="lightboxOpen = false" />
</template>

<style scoped>
.scene-image-block {
  margin: 10px 0 4px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--df-border, rgba(255, 255, 255, 0.12));
  background: var(--df-bg-soft, rgba(0, 0, 0, 0.2));
}

.scene-image-block img {
  display: block;
  width: 100%;
  height: auto;
  cursor: zoom-in;
}
</style>
