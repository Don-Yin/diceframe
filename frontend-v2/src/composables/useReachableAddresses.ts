import { computed, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { pairingApi } from '@/api/pairing'
import type { NetworkAddress } from '@/api/types'

/**
 * 服务端探测到的本机可达地址。
 *
 * 浏览器只知道自己访问用的那个 origin——GM 在本机打开的多半是 localhost，
 * 对手机毫无意义。候选地址只有服务端答得上来（GET /api/system/network）。
 *
 * 扫码登录与邀请/接管链接问的是同一件事「别的设备该连哪个地址」，所以共用这一份
 * 清单，而不是各自猜一套：`url` 是后端入口（App 配对用），`host` 用来替换任意
 * origin 的主机名（前端加入地址用，见 utils/shareLink 的 withHost）。
 *
 * 该接口仅对 owner 会话开放：配了访问密码又不是管理员会话时会 403。这时候清单为
 * 空、`error` 置位，调用方退回自己已知的地址即可——拿不到候选不该让二维码本身出
 * 不来，所以这里只记录错误，不抛也不弹提示。
 */
export function useReachableAddresses() {
  const addresses = ref<NetworkAddress[]>([])
  const loading = ref(false)
  const error = ref('')

  const hosts = computed(() => addresses.value.map((entry) => entry.host).filter(Boolean))
  const urls = computed(() => addresses.value.map((entry) => entry.url).filter(Boolean))

  async function load(): Promise<void> {
    loading.value = true
    try {
      addresses.value = (await pairingApi.networkAddresses()).addresses || []
      error.value = ''
    } catch (e: unknown) {
      addresses.value = []
      error.value = errorMessage(e)
    } finally {
      loading.value = false
    }
  }

  return { addresses, hosts, urls, loading, error, load }
}
