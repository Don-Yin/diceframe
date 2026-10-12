import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type {
  ApplicationHealthResponse,
  ApplicationRestartResponse,
  UpdateStatusResponse,
  UpdateDownloadResponse,
  UpdateApplyResponse,
} from '@/api/types'

// 单例：更新下载状态跨组件共享（设置页打开/关闭不丢失进行中的下载）。
const updateStatus = ref<UpdateStatusResponse | null>(null)
const reloadCountdown = ref<number | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null
let reloadTimer: ReturnType<typeof setTimeout> | null = null
let reloadAfterLauncherUpdate = false

const ACTIVE_STATES = new Set<UpdateStatusResponse['state']>(['downloading', 'verifying', 'applying', 'restarting'])
const DOWNLOAD_STATES = new Set<UpdateStatusResponse['state']>(['downloading', 'verifying'])
const RELOAD_DELAY_SECONDS = 5
const isDownloading = computed(() => DOWNLOAD_STATES.has(updateStatus.value?.state || 'idle'))
const isUpdateBusy = computed(() => ACTIVE_STATES.has(updateStatus.value?.state || 'idle'))

// 从更新弹窗的“去设置”进入时是否自动开始下载。仅在可写的 source、
// portable 或 docker-managed 安装、确有新版且无进行中任务时触发。
// 注意：state/version 反映的是上次更新的持久化结果，检测到新版本时不会重置。
// 若上次 state 残留为 done/staged（属于旧版本），不能据此拦截——否则弹窗“前往
// 设置”后永远不自动下载。只拦截真正进行中的任务，避免并发下载。
export function shouldAutoDownloadUpdate(
  kind: 'source' | 'portable' | 'docker' | null,
  state: string | undefined,
  focus: string,
  updateAvailable: boolean,
): boolean {
  if (!kind || focus !== 'update') return false
  if (state && ACTIVE_STATES.has(state as UpdateStatusResponse['state'])) return false
  return updateAvailable
}

export function updateStateForVersion(
  status: Pick<UpdateStatusResponse, 'state' | 'version'> | null,
  targetVersion?: string,
): UpdateStatusResponse['state'] {
  const normalize = (value?: string) => String(value || '').trim().replace(/^v/i, '')
  const statusVersion = normalize(status?.version)
  const target = normalize(targetVersion)
  return statusVersion && target && statusVersion === target ? status?.state || 'idle' : 'idle'
}

const downloadPercent = computed(() => {
  const s = updateStatus.value
  if (!s || !s.total_bytes) return 0
  return Math.min(100, Math.round((s.downloaded_bytes || 0) / s.total_bytes * 100))
})

function schedulePoll(): void {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
  if (ACTIVE_STATES.has(updateStatus.value?.state || 'idle')) {
    pollTimer = setTimeout(() => { void refreshStatus() }, 1500)
  }
}

function startReloadCountdown(): void {
  if (reloadTimer || typeof window === 'undefined') return
  reloadCountdown.value = RELOAD_DELAY_SECONDS
  const tick = () => {
    const remaining = reloadCountdown.value
    if (remaining === null) return
    if (remaining <= 1) {
      reloadCountdown.value = 0
      reloadTimer = null
      window.location.reload()
      return
    }
    reloadCountdown.value = remaining - 1
    reloadTimer = setTimeout(tick, 1000)
  }
  reloadTimer = setTimeout(tick, 1000)
}

function observeLauncherUpdateCompletion(): void {
  if (!reloadAfterLauncherUpdate) return
  const state = updateStatus.value?.state
  if (state === 'done') {
    reloadAfterLauncherUpdate = false
    startReloadCountdown()
  } else if (state === 'failed' || state === 'rolled-back') {
    reloadAfterLauncherUpdate = false
  }
}

async function refreshStatus(): Promise<void> {
  try {
    updateStatus.value = await api<UpdateStatusResponse>('/system/update/status')
    observeLauncherUpdateCompletion()
  } catch {
    // 静默：UI 保留上次状态，避免轮询期间偶发错误刷屏
  }
  schedulePoll()
}

async function startDownload(kind: 'source' | 'portable' | 'docker'): Promise<UpdateDownloadResponse> {
  const result = await api<UpdateDownloadResponse>(`/system/update/download?kind=${kind}`, { method: 'POST' })
  if (result.ok) {
    await refreshStatus()
  }
  return result
}

async function applyUpdate(): Promise<UpdateApplyResponse> {
  const launcherManaged = updateStatus.value?.kind === 'portable' || updateStatus.value?.kind === 'docker'
  const result = await api<UpdateApplyResponse>('/system/update/apply', { method: 'POST' })
  if (result.ok) {
    reloadAfterLauncherUpdate = launcherManaged
    await refreshStatus()
  }
  return result
}

async function restartApplication(): Promise<ApplicationRestartResponse> {
  return api<ApplicationRestartResponse>('/system/restart', { method: 'POST' })
}

async function waitForApplicationRestart(previousBootId: string, timeoutMs = 90_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 800))
    try {
      const health = await api<ApplicationHealthResponse>('/system/update/health')
      if (health.ok && health.boot_id && health.boot_id !== previousBootId) return true
    } catch {
      // The connection is expected to fail while the old process releases the port.
    }
  }
  return false
}

export function useUpdater() {
  return {
    updateStatus,
    reloadCountdown,
    isDownloading,
    isUpdateBusy,
    downloadPercent,
    refreshStatus,
    startDownload,
    applyUpdate,
    restartApplication,
    waitForApplicationRestart,
  }
}
