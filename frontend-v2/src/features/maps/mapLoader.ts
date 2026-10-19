import { api } from '@/api/client'
import { resolveMapBackgroundAsset } from '@/api/mapBackgrounds'
import type { MapData } from '@/api/types'

export interface MapLoaderDeps {
  request?: <T>(path: string) => Promise<T>
  resolveBackground?: (map: MapData) => Promise<MapData>
}

export async function loadMapProjection(gameKey: string, deps: MapLoaderDeps = {}): Promise<MapData> {
  if (!gameKey) throw new Error('missing-game-key')
  const request = deps.request || api
  const resolveBackground = deps.resolveBackground || resolveMapBackgroundAsset
  const map = await request<MapData>(`/games/${encodeURIComponent(gameKey)}/map`)
  return resolveBackground(map)
}

export function shouldApplyMapResponse(requestId: number, latestRequestId: number): boolean {
  return requestId === latestRequestId
}
