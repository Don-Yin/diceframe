import { api } from '@/api/client'
import type {
  NetworkAddressesResponse,
  PairedDeviceListResponse,
  PairingCodeResponse,
} from '@/api/types'

export const pairingApi = {
  /** 本机对外可达的候选地址；浏览器只知道自己访问用的 origin，二维码得用这个 */
  networkAddresses: () => api<NetworkAddressesResponse>('/system/network'),
  issueCode: () => api<PairingCodeResponse>('/pairing', { method: 'POST', body: '{}' }),
  listDevices: () => api<PairedDeviceListResponse>('/devices'),
  revokeDevice: (deviceId: string) =>
    api<{ ok: boolean }>(`/devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' }),
  revokeAllDevices: () =>
    api<{ ok: boolean; revoked: number }>('/devices/revoke-all', { method: 'POST', body: '{}' }),
}
