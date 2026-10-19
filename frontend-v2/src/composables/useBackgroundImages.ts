import { reactive, ref } from 'vue'

export type RuleBackgroundSlot =
  | 'scene-dnd5e'
  | 'scene-freeform-fantasy'
  | 'scene-freeform-coc'
  | 'scene-freeform-cyberpunk'
  | 'scene-freeform-wuxia'
  | 'scene-tavern-free'
export type BackgroundSlot = 'atmosphere' | RuleBackgroundSlot | 'ruins'

export interface BackgroundOption {
  id: BackgroundSlot
  titleKey:
    | 'backgroundAtmosphere'
    | 'backgroundRuleDnd5e'
    | 'backgroundRuleFantasy'
    | 'backgroundRuleCoc'
    | 'backgroundRuleCyberpunk'
    | 'backgroundRuleWuxia'
    | 'backgroundRuleTavern'
    | 'backgroundRuins'
  descriptionKey: 'backgroundAtmosphereHint' | 'backgroundRuleSceneHint' | 'backgroundRuinsHint'
}

export const backgroundOptions: readonly BackgroundOption[] = [
  { id: 'atmosphere', titleKey: 'backgroundAtmosphere', descriptionKey: 'backgroundAtmosphereHint' },
  { id: 'scene-dnd5e', titleKey: 'backgroundRuleDnd5e', descriptionKey: 'backgroundRuleSceneHint' },
  { id: 'scene-freeform-fantasy', titleKey: 'backgroundRuleFantasy', descriptionKey: 'backgroundRuleSceneHint' },
  { id: 'scene-freeform-coc', titleKey: 'backgroundRuleCoc', descriptionKey: 'backgroundRuleSceneHint' },
  { id: 'scene-freeform-cyberpunk', titleKey: 'backgroundRuleCyberpunk', descriptionKey: 'backgroundRuleSceneHint' },
  { id: 'scene-freeform-wuxia', titleKey: 'backgroundRuleWuxia', descriptionKey: 'backgroundRuleSceneHint' },
  { id: 'scene-tavern-free', titleKey: 'backgroundRuleTavern', descriptionKey: 'backgroundRuleSceneHint' },
  { id: 'ruins', titleKey: 'backgroundRuins', descriptionKey: 'backgroundRuinsHint' },
]

const DEFAULT_URLS: Record<BackgroundSlot, string> = {
  atmosphere: '/v2-assets/ui/dark-fantasy-atmosphere.jpg',
  'scene-dnd5e': '/v2-assets/ui/dnd-ashen-throne.png',
  'scene-freeform-fantasy': '/v2-assets/ui/rules/rule-freeform-fantasy.webp',
  'scene-freeform-coc': '/v2-assets/ui/rules/rule-freeform-coc.webp',
  'scene-freeform-cyberpunk': '/v2-assets/ui/rules/rule-freeform-cyberpunk.webp',
  'scene-freeform-wuxia': '/v2-assets/ui/rules/rule-freeform-wuxia.webp',
  'scene-tavern-free': '/v2-assets/ui/rules/rule-tavern-free.webp',
  ruins: '/v2-assets/ui/campaign-moonlit-ruins.jpg',
}

// Scene-image references are persisted by stable builtin IDs. Keep aliases
// used by the save-cover pool resolvable in the client so returning to the
// overview does not turn a valid builtin cover into the generic rule fallback.
const BUILTIN_SCENE_URLS: Record<string, string> = {
  dnd5e: '/v2-assets/ui/campaign-mountain-city.jpg',
  ashen_throne: '/v2-assets/ui/dnd-ashen-throne.png',
  mountain_city: '/v2-assets/ui/campaign-mountain-city.jpg',
  moonlit_ruins: '/v2-assets/ui/campaign-moonlit-ruins.jpg',
  dark_fantasy: '/v2-assets/ui/dark-fantasy-atmosphere.jpg',
  freeform_fantasy: '/v2-assets/ui/rules/rule-freeform-fantasy.webp',
  freeform_coc: '/v2-assets/ui/rules/rule-freeform-coc.webp',
  freeform_coc_harbor: '/v2-assets/ui/rules/rule-freeform-coc-harbor.webp',
  freeform_coc_town: '/v2-assets/ui/rules/rule-freeform-coc-town.webp',
  freeform_cyberpunk: '/v2-assets/ui/rules/rule-freeform-cyberpunk.webp',
  freeform_cyberpunk_alley: '/v2-assets/ui/rules/rule-freeform-cyberpunk-alley.webp',
  freeform_cyberpunk_rooftops: '/v2-assets/ui/rules/rule-freeform-cyberpunk-rooftops.webp',
  freeform_wuxia: '/v2-assets/ui/rules/rule-freeform-wuxia.webp',
  freeform_wuxia_mountains: '/v2-assets/ui/rules/rule-freeform-wuxia-mountains.webp',
  freeform_wuxia_riverside: '/v2-assets/ui/rules/rule-freeform-wuxia-riverside.webp',
  tavern_free: '/v2-assets/ui/rules/rule-tavern-free.webp',
}
const CSS_PROPERTIES: Partial<Record<BackgroundSlot, string>> = {
  atmosphere: '--df-bg-atmosphere-image',
  ruins: '--df-bg-ruins-image',
}
const DB_NAME = 'diceframe-local-appearance-v1'
const STORE_NAME = 'backgrounds'
const MAX_IMAGE_BYTES = 8 * 1024 * 1024
const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/avif'])

const previews = reactive<Record<BackgroundSlot, string>>({ ...DEFAULT_URLS })
const custom = reactive<Record<BackgroundSlot, boolean>>(
  Object.fromEntries(backgroundOptions.map(({ id }) => [id, false])) as Record<BackgroundSlot, boolean>,
)
const loading = ref(false)
let initialized = false
const objectUrls = new Map<BackgroundSlot, string>()
let activeSceneSlot: RuleBackgroundSlot = 'scene-dnd5e'

const RULE_SCENE_SLOTS: Record<string, RuleBackgroundSlot> = {
  dnd5e: 'scene-dnd5e',
  freeform_fantasy: 'scene-freeform-fantasy',
  freeform_coc: 'scene-freeform-coc',
  freeform_cyberpunk: 'scene-freeform-cyberpunk',
  freeform_wuxia: 'scene-freeform-wuxia',
  tavern_free: 'scene-tavern-free',
}

export function ruleSceneSlot(ruleId?: string): RuleBackgroundSlot {
  return RULE_SCENE_SLOTS[String(ruleId || '').trim()] || 'scene-freeform-fantasy'
}

export function ruleSceneUrl(ruleId?: string): string {
  return previews[ruleSceneSlot(ruleId)]
}

export function builtinSceneImageUrl(imageId?: string, fallbackRuleId?: string): string {
  return BUILTIN_SCENE_URLS[String(imageId || '').trim()] || ruleSceneUrl(fallbackRuleId)
}

export function ruleSceneStyle(ruleId?: string): Record<string, string> {
  return { '--df-bg-scene-image': `url("${ruleSceneUrl(ruleId).replace(/"/g, '%22')}")` }
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) request.result.createObjectStore(STORE_NAME)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Unable to open the appearance database'))
  })
}

async function readBlob(slot: string): Promise<Blob | undefined> {
  const db = await openDatabase()
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).get(slot)
      request.onsuccess = () => resolve(request.result instanceof Blob ? request.result : undefined)
      request.onerror = () => reject(request.error)
    })
  } finally {
    db.close()
  }
}

async function writeBlob(slot: string, blob?: Blob): Promise<void> {
  const db = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, 'readwrite')
      const store = transaction.objectStore(STORE_NAME)
      if (blob) store.put(blob, slot)
      else store.delete(slot)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error)
      transaction.onabort = () => reject(transaction.error)
    })
  } finally {
    db.close()
  }
}

function applyUrl(slot: BackgroundSlot, url: string, isCustom: boolean) {
  const previous = objectUrls.get(slot)
  if (previous && previous !== url) URL.revokeObjectURL(previous)
  if (url.startsWith('blob:')) objectUrls.set(slot, url)
  else objectUrls.delete(slot)
  previews[slot] = url
  custom[slot] = isCustom
  const cssProperty = CSS_PROPERTIES[slot]
  if (cssProperty) document.documentElement.style.setProperty(cssProperty, `url("${url.replace(/"/g, '%22')}")`)
  if (slot === activeSceneSlot) document.documentElement.style.setProperty('--df-bg-scene-image', `url("${url.replace(/"/g, '%22')}")`)
}

export function activateRuleBackground(ruleId?: string) {
  activeSceneSlot = ruleSceneSlot(ruleId)
  if (typeof document !== 'undefined') {
    document.documentElement.style.setProperty('--df-bg-scene-image', `url("${previews[activeSceneSlot].replace(/"/g, '%22')}")`)
  }
}

export async function initializeBackgroundImages() {
  if (initialized || typeof document === 'undefined' || typeof indexedDB === 'undefined') return
  initialized = true
  loading.value = true
  try {
    await Promise.all(backgroundOptions.map(async ({ id }) => {
      let blob = await readBlob(id)
      if (!blob && id === 'scene-dnd5e') {
        blob = await readBlob('scene')
        if (blob) {
          await writeBlob(id, blob)
          await writeBlob('scene')
        }
      }
      applyUrl(id, blob ? URL.createObjectURL(blob) : DEFAULT_URLS[id], Boolean(blob))
    }))
    activateRuleBackground()
  } catch {
    for (const { id } of backgroundOptions) applyUrl(id, DEFAULT_URLS[id], false)
  } finally {
    loading.value = false
  }
}

export function useBackgroundImages() {
  async function setBackground(slot: BackgroundSlot, file: File) {
    if (!ALLOWED_TYPES.has(file.type)) throw new Error('unsupported-image-type')
    if (file.size > MAX_IMAGE_BYTES) throw new Error('image-too-large')
    await writeBlob(slot, file)
    applyUrl(slot, URL.createObjectURL(file), true)
  }

  async function resetBackground(slot: BackgroundSlot) {
    await writeBlob(slot)
    applyUrl(slot, DEFAULT_URLS[slot], false)
  }

  async function resetAllBackgrounds() {
    await Promise.all(backgroundOptions.map(({ id }) => writeBlob(id)))
    for (const { id } of backgroundOptions) applyUrl(id, DEFAULT_URLS[id], false)
  }

  return {
    options: backgroundOptions,
    previews,
    custom,
    loading,
    initialize: initializeBackgroundImages,
    activateRule: activateRuleBackground,
    ruleSceneUrl,
    setBackground,
    resetBackground,
    resetAllBackgrounds,
  }
}
