import { nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn(async (path: string, _init?: RequestInit): Promise<Record<string, unknown>> => {
  if (path.startsWith('/lorebooks/activation-preview')) {
    return { ok: true, trace: [{ entry_id: 'public', final_state: 'included' }, { entry_id: '', final_state: 'hidden' }] }
  }
  return { ok: true, projections: {}, summary: { total: 0, visible: 0, public: 0, character_only: 0, gm_secret: 0 } }
  }) }))

vi.mock('@/api/client', () => ({ api: apiMock, errorMessage: (error: unknown) => String(error) }))
vi.mock('@/peer/game/bridge', () => ({ activePeerGameClient: () => null }))

import { useLorePerspective } from '../src/features/lorebook/useLorePerspective'

describe('useLorePerspective activation preview', () => {
  it('posts the action and viewer payload, retaining the backend trace', async () => {
    const perspective = useLorePerspective(ref('world-1'), ref('game-1'), ref([{ user_id: 'u1', character_name: 'Laila' }]))
    perspective.activationText.value = 'open the sealed door'
    await perspective.refreshActivationPreview()
    await nextTick()

    const request = apiMock.mock.calls.find(([path]) => path === '/lorebooks/activation-preview')
    expect(request).toBeTruthy()
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      game_key: 'game-1',
      action_text: 'open the sealed door',
      viewer: { is_gm: true },
    })
    expect(perspective.activation.value?.trace?.[0].entry_id).toBe('public')
  })
})
