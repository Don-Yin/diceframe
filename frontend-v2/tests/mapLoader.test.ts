import { describe, expect, it, vi } from 'vitest'
import { loadMapProjection, shouldApplyMapResponse } from '../src/features/maps/mapLoader'

describe('map projection loader', () => {
  it('requests the game map and resolves its protected background through the owner', async () => {
    const request = vi.fn().mockResolvedValue({ locations: [], active_map: null })
    const resolveBackground = vi.fn(async (map) => ({ ...map, current_scene: 'station' }))

    const result = await loadMapProjection('web|room/one', { request, resolveBackground })

    expect(request).toHaveBeenCalledWith('/games/web%7Croom%2Fone/map')
    expect(resolveBackground).toHaveBeenCalledOnce()
    expect(result.current_scene).toBe('station')
  })

  it('rejects stale responses from replacing a selected game', () => {
    expect(shouldApplyMapResponse(1, 2)).toBe(false)
    expect(shouldApplyMapResponse(2, 2)).toBe(true)
  })
})
