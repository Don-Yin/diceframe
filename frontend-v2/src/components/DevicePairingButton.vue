<script setup lang="ts">
/**
 * 顶栏「手机扫码登录」入口：圆形 quaternary 按钮，视觉与公告/主题按钮对齐。
 * 只负责发出 open 事件，二维码与配对逻辑仍归 DevicePairingModal/DevicePairingPanel。
 */
import { NButton, NIcon } from 'naive-ui'
import { QrCodeOutline } from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'

defineEmits<{ open: [] }>()
const { t } = useLocale()
</script>

<template>
  <NButton
    circle
    quaternary
    class="theme-toggle"
    :title="t('pairingTitle')"
    :aria-label="t('pairingTitle')"
    @click="$emit('open')"
  >
    <template #icon>
      <NIcon size="18">
        <QrCodeOutline />
      </NIcon>
    </template>
  </NButton>
</template>
