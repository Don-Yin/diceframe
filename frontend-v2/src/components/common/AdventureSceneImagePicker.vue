<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { SCENE_IMAGE_ACCEPT, validateSceneImageFile } from '@/api/sceneImages'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{
  modelValue: File | null
  defaultUrl: string
}>()
const emit = defineEmits<{
  'update:modelValue': [value: File | null]
}>()
const { t } = useLocale()
const input = ref<HTMLInputElement | null>(null)
const localPreview = ref('')
const validationError = ref('')
const preview = computed(() => localPreview.value || props.defaultUrl)
const previewStyle = computed(() => ({ backgroundImage: `url("${preview.value.replace(/"/g, '%22')}")` }))

function releasePreview() {
  if (localPreview.value) URL.revokeObjectURL(localPreview.value)
  localPreview.value = ''
}

watch(() => props.modelValue, (file) => {
  releasePreview()
  if (file) localPreview.value = URL.createObjectURL(file)
}, { immediate: true })

function selectFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file) return
  try {
    validateSceneImageFile(file)
    validationError.value = ''
    emit('update:modelValue', file)
  } catch (error) {
    validationError.value = error instanceof Error && error.message === 'scene-image-too-large'
      ? t('scene-image-too-large')
      : t('unsupported-scene-image-type')
  }
}

onBeforeUnmount(releasePreview)
</script>

<template>
  <div class="scene-image-picker">
    <div class="scene-image-picker-preview" :style="previewStyle">
      <span>{{ modelValue ? t('sceneImageCustomBadge') : t('sceneImageDefaultBadge') }}</span>
    </div>
    <div class="scene-image-picker-copy">
      <strong>{{ t('sceneImageTitle') }}</strong>
      <small>{{ t('sceneImageHint') }}</small>
      <small v-if="validationError" class="error">{{ validationError }}</small>
      <div class="actions">
        <button type="button" :class="{ primary: !modelValue }" @click="emit('update:modelValue', null)">{{ t('sceneImageUseDefault') }}</button>
        <button type="button" :class="{ primary: modelValue }" @click="input?.click()">{{ t('sceneImageUpload') }}</button>
      </div>
    </div>
    <input ref="input" hidden type="file" :accept="SCENE_IMAGE_ACCEPT" @change="selectFile">
  </div>
</template>
