<script setup lang="ts">
/**
 * 扫码配对面板：出示二维码让 DiceFrame App 扫码登录，并管理已配对设备。
 *
 * 为什么地址要问服务端：GM 在本机打开的多半是 localhost，直接把 location.origin
 * 编进二维码，手机扫到的是一个它永远连不上的地址。候选地址只有服务端知道，走
 * useReachableAddresses——邀请/接管链接问的是同一件事，共用同一份清单。
 *
 * 地址选择器与二维码取景卡片也是共享组件（AddressPicker / QrStage），两个扫码
 * 弹窗因此保持同一套排版。
 *
 * 配对码本身是一次性、短时效的，过期后本面板不续期、只重新签发。
 */
import { computed, onUnmounted, ref } from 'vue'
import { NButton, NIcon, NSpin, NTag } from 'naive-ui'
import { PhonePortraitOutline, QrCodeOutline, TrashOutline } from '@vicons/ionicons5'

import AddressPicker from '@/components/common/AddressPicker.vue'
import QrStage from '@/components/common/QrStage.vue'
import { pairingApi } from '@/api/pairing'
import { errorMessage } from '@/api/client'
import { currentBackendUrl } from '@/api/connection'
import { buildPairingPayload, normalizePublicBaseUrl } from '@/utils/shareLink'
import { useConfirm } from '@/composables/useConfirm'
import { useLocale } from '@/composables/useLocale'
import { useReachableAddresses } from '@/composables/useReachableAddresses'
import { useToast } from '@/composables/useToast'
import type { PairedDevice } from '@/api/types'

const props = defineProps<{ publicBaseUrl?: string }>()

const { t } = useLocale()
const toast = useToast()
const { confirm } = useConfirm()

// 候选地址与邀请/接管链接共用同一份服务端探测结果。App 配对连的是后端入口，
// 所以这里取 url 而不是 host。
const {
  urls: reachableUrls,
  loading: addressesLoading,
  error: addressesError,
  load: loadReachable,
} = useReachableAddresses()
const selectedAddress = ref('')
const code = ref('')
const codeIssuing = ref(false)
const secondsLeft = ref(0)
const devices = ref<PairedDevice[]>([])
const devicesLoading = ref(false)
// 已配对设备默认折起来：主界面只需要二维码，设备清单是点开才看的管理面。
const devicesOpen = ref(false)
let countdown: ReturnType<typeof setInterval> | undefined

const payload = computed(() =>
  code.value && selectedAddress.value ? buildPairingPayload(selectedAddress.value, code.value) : '',
)

/** 配了公网地址/隧道时它才是手机真正能连上的入口，排在候选首位。 */
const publicUrl = computed(() =>
  props.publicBaseUrl ? normalizePublicBaseUrl(props.publicBaseUrl) : '',
)
const addresses = computed(() => [
  ...new Set([...(publicUrl.value ? [publicUrl.value] : []), ...reachableUrls.value]),
])
const addressOptions = computed(() => addresses.value.map((url) => ({ label: url, value: url })))

function stopCountdown() {
  if (countdown !== undefined) clearInterval(countdown)
  countdown = undefined
}

onUnmounted(stopCountdown)

function expireCode() {
  stopCountdown()
  code.value = ''
  secondsLeft.value = 0
}

async function loadAddresses() {
  await loadReachable()
  // 配对面板没有别的地址来源可退，拿不到候选要让 GM 知道原因。
  if (addressesError.value) toast.error(addressesError.value)
  if (!addresses.value.includes(selectedAddress.value)) {
    selectedAddress.value = addresses.value[0] || normalizePublicBaseUrl(currentBackendUrl())
  }
}

async function loadDevices() {
  devicesLoading.value = true
  try {
    devices.value = (await pairingApi.listDevices()).devices || []
  } catch (e: unknown) {
    toast.error(errorMessage(e))
  } finally {
    devicesLoading.value = false
  }
}

async function issueCode() {
  if (!selectedAddress.value) await loadAddresses()
  codeIssuing.value = true
  try {
    const result = await pairingApi.issueCode()
    code.value = result.code
    secondsLeft.value = Math.max(0, Math.round(result.expires_in))
    stopCountdown()
    countdown = setInterval(() => {
      secondsLeft.value -= 1
      if (secondsLeft.value <= 0) expireCode()
    }, 1000)
  } catch (e: unknown) {
    toast.error(errorMessage(e))
  } finally {
    codeIssuing.value = false
  }
}

async function revokeDevice(device: PairedDevice) {
  const label = device.label || t('pairingUnnamedDevice')
  if (!(await confirm({ content: t('pairingRevokeConfirm', { name: label }), type: 'error' }))) return
  try {
    await pairingApi.revokeDevice(device.id)
    toast.success(t('pairingRevoked', { name: label }))
    await loadDevices()
  } catch (e: unknown) {
    toast.error(errorMessage(e))
  }
}

async function revokeAll() {
  if (!(await confirm({ content: t('pairingRevokeAllConfirm'), type: 'error' }))) return
  try {
    const result = await pairingApi.revokeAllDevices()
    toast.success(t('pairingRevokedAll', { count: result.revoked }))
    await loadDevices()
  } catch (e: unknown) {
    toast.error(errorMessage(e))
  }
}

function formatTime(value: string): string {
  if (!value) return t('pairingNeverSeen')
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

/** 首次展开面板时才拉数据：设置页其它区块不该为这里付网络成本 */
async function initialize() {
  await Promise.all([loadAddresses(), loadDevices()])
}

defineExpose({ initialize })
</script>

<template>
  <section class="pairing-panel">
    <p class="pairing-desc">{{ t('pairingHelp') }}</p>

    <AddressPicker
      v-model:value="selectedAddress"
      :options="addressOptions"
      :label="t('pairingAddressLabel')"
      :hint="t('pairingAddressHint')"
      :placeholder="t('pairingAddressPlaceholder')"
      :loading="addressesLoading"
      :busy="devicesLoading"
      @update:value="expireCode"
      @refresh="initialize"
    />

    <QrStage :value="payload">
      <template #badge>
        <NTag class="pairing-expire-tag" type="warning" size="small" round>
          {{ t('pairingExpiresIn', { seconds: secondsLeft }) }}
        </NTag>
      </template>
      <template #placeholder>
        <NIcon :component="QrCodeOutline" size="40" />
        <p class="muted">{{ t('pairingIdleHint') }}</p>
      </template>
      <div v-if="payload" class="pairing-qr-meta">
        <!-- 扫码失败时的兜底：配对码本身可以在 App 里手输 -->
        <code class="pairing-code">{{ code }}</code>
        <p class="muted">{{ t('pairingScanHint') }}</p>
      </div>
      <NButton
        type="primary"
        class="pairing-generate-btn"
        :loading="codeIssuing"
        :disabled="!selectedAddress"
        @click="issueCode"
      >
        <template #icon><NIcon :component="QrCodeOutline" /></template>
        {{ code ? t('pairingRegenerate') : t('pairingGenerate') }}
      </NButton>
    </QrStage>

    <div class="pairing-devices">
      <button
        type="button"
        class="pairing-devices-toggle"
        :aria-expanded="devicesOpen"
        @click="devicesOpen = !devicesOpen"
      >
        <NIcon :component="PhonePortraitOutline" />
        <strong>{{ t('pairingDevicesTitle') }}</strong>
        <span class="pairing-devices-count">{{ devices.length }}</span>
        <span class="pairing-devices-chevron" aria-hidden="true">{{ devicesOpen ? '▾' : '›' }}</span>
      </button>
      <template v-if="devicesOpen">
        <div class="pairing-devices-head">
          <NButton v-if="devices.length" size="small" quaternary type="error" @click="revokeAll">
            {{ t('pairingRevokeAll') }}
          </NButton>
        </div>
        <NSpin :show="devicesLoading">
          <div v-if="devices.length" class="pairing-device-list">
            <div v-for="device in devices" :key="device.id" class="pairing-device-row">
              <NIcon :component="PhonePortraitOutline" />
              <div class="pairing-device-text">
                <strong>{{ device.label || t('pairingUnnamedDevice') }}</strong>
                <small>{{ t('pairingLastSeen', { at: formatTime(device.last_seen_at) }) }}</small>
              </div>
              <NButton size="tiny" quaternary type="error" @click="revokeDevice(device)">
                <template #icon><NIcon :component="TrashOutline" /></template>
                {{ t('pairingRevoke') }}
              </NButton>
            </div>
          </div>
          <p v-else-if="!devicesLoading" class="muted">{{ t('pairingNoDevices') }}</p>
        </NSpin>
      </template>
    </div>
  </section>
</template>

<style scoped>
.pairing-panel{margin-top:0;padding-top:0}
.pairing-desc{margin:0 0 18px;color:var(--df-text-muted);font-size:13px;line-height:1.6}

/* 地址选择器与二维码取景卡片的排版都在共享组件里（AddressPicker / QrStage），
   这里只留配对特有的东西：过期标签、配对码、出码按钮。 */
.pairing-expire-tag{align-self:center}
.pairing-qr-meta{display:flex;flex-direction:column;align-items:center;gap:6px}
.pairing-qr-meta p{margin:0;max-width:320px;line-height:1.6;font-size:12px}
.pairing-code{font-family:var(--df-font-mono);font-size:18px;letter-spacing:2px;background:color-mix(in srgb,var(--df-accent) 12%,transparent);padding:4px 10px;border-radius:6px}
.pairing-generate-btn{width:100%}
.pairing-devices{margin-top:6px;border-top:1px solid var(--df-border-soft);padding-top:12px}
.pairing-devices-toggle{display:flex;align-items:center;gap:8px;width:100%;min-height:40px;padding:6px 10px;border:1px solid var(--df-border-soft);border-radius:8px;background:var(--df-control-bg);color:var(--df-text-secondary);cursor:pointer}
.pairing-devices-toggle strong{font-weight:700}
.pairing-devices-count{min-width:20px;padding:1px 6px;border-radius:999px;background:color-mix(in srgb,var(--df-accent) 16%,transparent);font-size:12px;text-align:center}
.pairing-devices-chevron{margin-left:auto;color:var(--df-text-muted)}
.pairing-devices-head{display:flex;align-items:center;justify-content:flex-end;gap:12px;margin:10px 0 8px}
.pairing-device-list{display:flex;flex-direction:column;gap:8px}
.pairing-device-row{display:flex;align-items:center;gap:10px;padding:8px 12px;border:1px solid var(--df-border-soft);border-radius:8px}
.pairing-device-text{display:flex;flex-direction:column;flex:1;min-width:0}
.pairing-device-text small{color:var(--df-text-muted)}
</style>
