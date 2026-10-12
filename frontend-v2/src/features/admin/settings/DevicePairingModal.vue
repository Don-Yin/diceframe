<script setup lang="ts">
/**
 * 手机扫码登录弹窗：顶栏二维码按钮的主入口。
 *
 * 只做承载：地址候选、二维码、配对码与设备清单全部复用现有
 * DevicePairingPanel（同一个 pairingApi），这里不新增 pairing 状态或请求。
 * 面板的 initialize 只在弹窗真正打开时调用，所以其余页面不为它付网络成本。
 */
import { onMounted, ref } from 'vue'
import Modal from '@/components/ui/Modal.vue'
import DevicePairingPanel from '@/features/admin/settings/DevicePairingPanel.vue'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useLocale } from '@/composables/useLocale'

const emit = defineEmits<{ close: [] }>()
const { t } = useLocale()
const settings = useSettingsStore()
const panel = ref<InstanceType<typeof DevicePairingPanel> | null>(null)

onMounted(async () => {
  // public_base_url 决定候选地址的首选入口（公网/隧道）。配置页之外还没有人
  // 拉过 config 时先补一次，否则二维码只会给出局域网地址。
  if (!settings.config.access_password) await settings.load()
  await panel.value?.initialize()
})
</script>

<template>
  <Modal
    :title="t('pairingTitle')"
    dialog-class="qr-share-dialog"
    @close="emit('close')"
  >
    <DevicePairingPanel ref="panel" :public-base-url="settings.config.public_base_url" />
  </Modal>
</template>
