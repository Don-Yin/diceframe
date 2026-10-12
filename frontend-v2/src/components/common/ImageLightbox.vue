<script setup lang="ts">
defineProps<{ open: boolean; src: string; alt?: string }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="image-lightbox" role="dialog" aria-modal="true" @click.self="emit('close')">
      <button class="image-lightbox-close" type="button" aria-label="Close" @click="emit('close')">×</button>
      <img :src="src" :alt="alt || ''" @click.stop>
    </div>
  </Teleport>
</template>

<style scoped>
.image-lightbox{position:fixed;inset:0;z-index:3000;display:grid;place-items:center;padding:28px;background:rgba(0,0,0,.82);cursor:zoom-out}
.image-lightbox img{max-width:96vw;max-height:92vh;object-fit:contain;border-radius:10px;box-shadow:0 16px 60px rgba(0,0,0,.5);cursor:default}
.image-lightbox-close{position:absolute;top:12px;right:16px;border:0;background:transparent;color:#fff;font-size:32px;line-height:1;cursor:pointer}
</style>
