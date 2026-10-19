import { api, apiBlob } from '@/api/client'
import type { SceneImageRef } from '@/api/types'
import { builtinSceneImageUrl, ruleSceneUrl } from '@/composables/useBackgroundImages'

export const MAX_SCENE_IMAGE_BYTES = 8 * 1024 * 1024
export const SCENE_IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp'

export interface SceneImageUploadResponse {
  ok: boolean
  error?: string
  scene_image?: SceneImageRef
}

const SCENE_IMAGE_KINDS = new Set<SceneImageRef['kind']>(['builtin', 'upload', 'plugin', 'asset', 'generated'])

// Keep the client preview in step with the server's built-in pool when an
// older content summary only exposes its legacy `scene_image` field.  A
// content pack can still provide an explicit `scene_images` list; that list
// always wins and is never expanded here.
const BUILTIN_SCENE_IMAGE_VARIANTS: Record<string, string[]> = {
  dnd5e: ['dnd5e', 'ashen_throne', 'moonlit_ruins'],
  dnd2024_srd: ['dnd5e', 'ashen_throne', 'moonlit_ruins'],
  freeform_fantasy: ['freeform_fantasy', 'mountain_city', 'dark_fantasy'],
  freeform_coc: ['freeform_coc', 'freeform_coc_harbor', 'freeform_coc_town'],
  freeform_cyberpunk: ['freeform_cyberpunk', 'freeform_cyberpunk_alley', 'freeform_cyberpunk_rooftops'],
  freeform_wuxia: ['freeform_wuxia', 'freeform_wuxia_mountains', 'freeform_wuxia_riverside'],
  tavern_free: ['tavern_free', 'moonlit_ruins', 'mountain_city'],
}

/**
 * Return a de-duplicated, backwards-compatible content cover pool.
 *
 * `scene_image` is the original single-cover contract and remains first so
 * old templates keep their exact appearance. New content may add
 * `scene_images`; invalid or repeated entries are ignored at the UI boundary
 * and the server still remains the authority when creating a game.
 */
export function sceneImageCandidates(
  primary?: SceneImageRef | null,
  variants?: readonly SceneImageRef[] | null,
  expandBuiltinVariants = true,
): SceneImageRef[] {
  const explicitVariants = variants && variants.length > 0
    ? variants
    : (expandBuiltinVariants && primary?.kind === 'builtin'
      ? BUILTIN_SCENE_IMAGE_VARIANTS[primary.id || '']
        ?.slice(1)
        .map(id => ({ kind: 'builtin' as const, id })) || []
      : [])
  const candidates = [primary, ...explicitVariants]
  const result: SceneImageRef[] = []
  const seen = new Set<string>()
  for (const candidate of candidates) {
    if (!candidate || !SCENE_IMAGE_KINDS.has(candidate.kind)) continue
    const identity = JSON.stringify(candidate)
    if (seen.has(identity)) continue
    seen.add(identity)
    result.push(candidate)
  }
  return result
}

/**
 * Select one cover consistently for a create session.
 *
 * A stable key is intentional: Vue watchers can run more than once while
 * catalogs load, so using Math.random() here would make the preview jump and
 * could disagree with the reference sent to the create endpoint. Callers can
 * generate one key per create draft to get a different default for each new
 * adventure while keeping that draft stable.
 */
export function pickSceneImageReference(
  primary?: SceneImageRef | null,
  variants?: readonly SceneImageRef[] | null,
  selectionKey = '',
  expandBuiltinVariants = true,
): SceneImageRef | undefined {
  const candidates = sceneImageCandidates(primary, variants, expandBuiltinVariants)
  if (!candidates.length) return undefined
  if (candidates.length === 1 || !selectionKey) return candidates[0]
  let hash = 2166136261
  for (let index = 0; index < selectionKey.length; index += 1) {
    hash ^= selectionKey.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  const offset = (hash >>> 0) % candidates.length
  return candidates[offset]
}

/**
 * Overview cards are mounted again whenever the user returns from another
 * route.  Keep custom scene blobs alive for the app session so that a return
 * does not fetch every cover again.  The cache is deliberately bounded; the
 * overview prunes keys that disappeared from the archive and the LRU cap
 * protects long lived sessions with many saves.
 */
const GAME_SCENE_CACHE_LIMIT = 48
interface GameSceneCacheEntry {
  signature: string
  url: string
  touchedAt: number
}
const gameSceneCache = new Map<string, GameSceneCacheEntry>()
const gameScenePending = new Map<string, Promise<string>>()

function sceneReferenceSignature(reference: SceneImageRef | null | undefined, fallbackRuleId: string): string {
  return JSON.stringify({ reference: reference || null, fallbackRuleId })
}

function evictGameSceneCache() {
  while (gameSceneCache.size > GAME_SCENE_CACHE_LIMIT) {
    const oldest = [...gameSceneCache.entries()].sort(([, a], [, b]) => a.touchedAt - b.touchedAt)[0]
    if (!oldest) return
    gameSceneCache.delete(oldest[0])
    revokeSceneImageUrl(oldest[1].url)
  }
}

function encodeAssetPath(path: string): string {
  return path.split('/').filter(Boolean).map(encodeURIComponent).join('/')
}

export function validateSceneImageFile(file: File): void {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('unsupported-scene-image-type')
  if (file.size > MAX_SCENE_IMAGE_BYTES) throw new Error('scene-image-too-large')
}

export async function fileToBase64(file: File): Promise<string> {
  validateSceneImageFile(file)
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  let binary = ''
  const chunkSize = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return btoa(binary)
}

export async function uploadSceneImage(file: File): Promise<SceneImageRef> {
  const result = await api<SceneImageUploadResponse>('/scene-images', {
    method: 'POST',
    body: JSON.stringify({ file_data: await fileToBase64(file), file_name: file.name }),
  })
  if (!result.ok || !result.scene_image) throw new Error(result.error || 'scene-image-upload-failed')
  return result.scene_image
}

export async function resolveSceneImageUrl(reference: SceneImageRef | undefined, fallbackRuleId = ''): Promise<string> {
  if (!reference) return ruleSceneUrl(fallbackRuleId)
  if (reference.kind === 'builtin') return builtinSceneImageUrl(reference.id, fallbackRuleId)
  let path = ''
  if (reference.kind === 'upload' && reference.asset_id) {
    path = `/scene-images/${encodeURIComponent(reference.asset_id)}`
  } else if (reference.kind === 'generated' && reference.asset_id) {
    path = `/generated-images/${encodeURIComponent(reference.asset_id)}`
  } else if (reference.kind === 'plugin' && reference.plugin_id && reference.path) {
    path = `/plugins/assets/${encodeURIComponent(reference.plugin_id)}/${encodeAssetPath(reference.path)}`
  }
  if (!path) return ruleSceneUrl(fallbackRuleId)
  const response = await apiBlob(path)
  return URL.createObjectURL(await response.blob())
}

export async function resolveGameSceneImageUrl(
  gameKey: string,
  fallbackRuleId = '',
  useDefault = false,
  overviewReference?: SceneImageRef | null,
): Promise<string> {
  // The overview already receives the scene reference in /games.  Built-ins
  // can be resolved synchronously from the local asset map and uploaded /
  // generated covers are cached by game key + reference signature.  Passing
  // null explicitly is meaningful: it tells this helper that the overview
  // has no custom reference and should use the rule fallback without making
  // the legacy scene-image request.
  if (overviewReference !== undefined) {
    if (!overviewReference || overviewReference.kind === 'builtin') {
      return builtinSceneImageUrl(overviewReference?.id, fallbackRuleId)
    }
    const signature = sceneReferenceSignature(overviewReference, fallbackRuleId)
    const cached = gameSceneCache.get(gameKey)
    if (cached?.signature === signature) {
      cached.touchedAt = Date.now()
      return cached.url
    }
    const pendingKey = `${gameKey}\u0000${signature}`
    const pending = gameScenePending.get(pendingKey)
    if (pending) return pending
    const request = resolveSceneImageUrl(overviewReference, fallbackRuleId).then(url => {
      const previous = gameSceneCache.get(gameKey)
      if (previous && previous.url !== url) revokeSceneImageUrl(previous.url)
      gameSceneCache.set(gameKey, { signature, url, touchedAt: Date.now() })
      evictGameSceneCache()
      return url
    }).finally(() => {
      gameScenePending.delete(pendingKey)
    })
    gameScenePending.set(pendingKey, request)
    return request
  }

  try {
    const response = await apiBlob(`/games/${encodeURIComponent(gameKey)}/scene-image${useDefault ? '?default=1' : ''}`)
    return URL.createObjectURL(await response.blob())
  } catch {
    return ruleSceneUrl(fallbackRuleId)
  }
}

export function pruneGameSceneImageCache(activeGameKeys: Iterable<string>): void {
  const active = new Set(activeGameKeys)
  for (const [gameKey, entry] of gameSceneCache) {
    if (active.has(gameKey)) continue
    gameSceneCache.delete(gameKey)
    revokeSceneImageUrl(entry.url)
  }
}

export function sceneImageStyle(url: string): Record<string, string> {
  return { '--df-bg-scene-image': `url("${url.replace(/"/g, '%22')}")` }
}

export function revokeSceneImageUrl(url: string): void {
  if (url.startsWith('blob:')) URL.revokeObjectURL(url)
}
