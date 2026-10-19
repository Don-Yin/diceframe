import { computed, nextTick, onScopeDispose, ref, watch, type Ref } from 'vue'
import { api } from '@/api/client'
import type { AdventureSummary, AdventuresResponse, RuleSummary, WorldTemplateSummary } from '@/api/types'
import type { MessageKey } from '@/i18n'
import { adventureMatchesRule } from '@/features/adventures/compatibility'

export function adventureKey(item: AdventureSummary): string {
  return JSON.stringify([item.source_kind || (item.custom ? 'user' : 'builtin'), item.source_id || '', item.adventure_id])
}

/** Owns catalogue selection and launch handoff; server remains the compatibility authority. */
export function useAdventureSelection(options: {
  rule: Ref<string>; world: Ref<string>; language: Ref<string>; mode: Ref<string>; supported: Ref<boolean>
  request?: typeof api
  setRule?: (id: string) => void
}) {
  const request = options.request || api
  const catalogue = ref<AdventureSummary[]>([])
  const adventures = ref<AdventureSummary[]>([])
  const selectedKey = ref('')
  const moduleId = ref('')
  const playMode = ref<'free' | 'adventure' | 'gal'>('free')
  const loading = ref(false)
  const loadIssue = ref<MessageKey | ''>('')
  let sequence = 0
  let discoverySequence = 0
  let launchSequence = 0
  let initializing = false
  const availableModuleAdventures = computed(() => catalogue.value.filter(item => moduleId.value
    ? item.source_kind === 'plugin' && item.source_id === moduleId.value
    : item.source_kind !== 'plugin'))
  // The contextual list is the only authority for launch/binding.  The
  // discovery catalogue is still useful for explaining a blocked deep link
  // (for example when its fixed world is not installed), so keep it as a
  // display fallback without letting it make an adventure launchable.
  const selectedProjection = computed(() => adventures.value.find(item => adventureKey(item) === selectedKey.value))
  const selectedAdventure = computed(() => selectedProjection.value || catalogue.value.find(item => adventureKey(item) === selectedKey.value))
  const issue = computed<MessageKey | ''>(() => {
    if (playMode.value === 'free' || playMode.value === 'gal') return ''
    if (loadIssue.value) return loadIssue.value
    if (!selectedKey.value) return 'adventureSelectionRequired'
    if (selectedKey.value && !selectedProjection.value) return loading.value ? '' : 'adventureLaunchUnavailable'
    if (selectedProjection.value?.compatibility === 'incompatible' || !options.supported.value) return 'adventureLaunchIncompatible'
    return ''
  })
  const ready = computed(() => !loading.value && playMode.value === 'adventure' && !issue.value && selectedProjection.value?.compatibility === 'compatible')
  const bindingPayload = computed(() => {
    const item = selectedProjection.value
    return item && playMode.value === 'adventure' ? {
      adventure_id: item.adventure_id,
      adventure_source_kind: item.source_kind || (item.custom ? 'user' : 'builtin'),
      adventure_source_id: item.source_id || '',
    } : { adventure_id: '', adventure_source_kind: '', adventure_source_id: '' }
  })

  async function reload() {
    if (initializing) return
    const current = ++sequence
    loadIssue.value = ''
    if (options.mode.value !== 'template') {
      adventures.value = []
      loading.value = false
      return
    }
    loading.value = true
    try {
      const result = await request<AdventuresResponse>(`/adventures?rule_id=${encodeURIComponent(options.rule.value)}&world_id=${encodeURIComponent(options.world.value)}&language=${encodeURIComponent(options.language.value)}`)
      if (current !== sequence) return
      if (!result.ok) throw new Error('catalogue unavailable')
      adventures.value = result.adventures || []
    } catch {
      if (current !== sequence) return
      adventures.value = []
      loadIssue.value = 'adventureLaunchUnavailable'
    } finally {
      if (current === sequence) loading.value = false
    }
  }

  async function discover() {
    const current = ++discoverySequence
    if (options.mode.value !== 'template') { catalogue.value = []; return }
    try {
      const result = await request<AdventuresResponse>(`/adventures?language=${encodeURIComponent(options.language.value)}`)
      if (current === discoverySequence) catalogue.value = result.ok ? result.adventures || [] : []
    } catch { if (current === discoverySequence) catalogue.value = [] }
  }

  function selectPlayMode(value: 'free' | 'adventure' | 'gal') {
    playMode.value = value
    if (value !== 'adventure') {
      ++launchSequence
      ++sequence
      initializing = false
      loading.value = false
      selectedKey.value = ''; loadIssue.value = ''
    }
  }
  watch(moduleId, () => { if (!initializing) { selectedKey.value = ''; loadIssue.value = '' } })
  watch(selectedKey, value => {
    if (!initializing && value && selectedAdventure.value) loadIssue.value = ''
  })
  watch([options.language, options.mode], discover, { immediate: true })
  watch([options.rule, options.world, options.language, options.mode], () => {
    if (selectedKey.value) void reload()
  }, { immediate: true })

  async function initializeLaunch(query: Record<string, unknown>, rules: RuleSummary[], worlds: WorldTemplateSummary[]) {
    const id = typeof query.adventure_id === 'string' ? query.adventure_id : ''
    if (!id) return
    const launch = ++launchSequence
    const sourceId = typeof query.module_id === 'string' ? query.module_id : ''
    const language = options.language.value
    const isCurrent = () => launch === launchSequence && sourceId === moduleId.value && language === options.language.value
    initializing = true
    ++sequence
    loading.value = true
    playMode.value = 'adventure'
    moduleId.value = sourceId
    try {
      const catalog = await request<AdventuresResponse>(`/adventures?language=${encodeURIComponent(options.language.value)}`)
      if (!isCurrent()) return
      if (!catalog.ok) throw new Error('catalogue unavailable')
      const matches = catalog.adventures.filter(item => item.adventure_id === id && (moduleId.value
        ? item.source_kind === 'plugin' && item.source_id === moduleId.value
        : item.source_kind !== 'plugin'))
      if (matches.length !== 1) throw new Error('source unavailable or ambiguous')
      const item = matches[0]!
      selectedKey.value = adventureKey(item)
      catalogue.value = catalog.adventures || []
      const compatibleRules = rules.filter(rule => adventureMatchesRule(item, rule))
      if (!compatibleRules.length) { loadIssue.value = 'adventureLaunchIncompatible'; return }
      const targetWorld = worlds.find(world => String(world.world_id || world.id) === item.recommended_world_id)
      if (item.world_policy === 'fixed' && !targetWorld) { loadIssue.value = 'adventureLaunchUnavailable'; return }
      // Apply the world first: CreateView's world-default rule watcher runs before
      // reload, while this explicit rule choice is restored after that flush.
      if (targetWorld) options.world.value = String(targetWorld.world_id || targetWorld.id)
      const chosenRule = compatibleRules.find(rule => rule.rule_id === options.rule.value) || compatibleRules[0]!
      await nextTick()
      if (!isCurrent()) return
      if (options.setRule) options.setRule(chosenRule.rule_id)
      else options.rule.value = chosenRule.rule_id
      await nextTick()
      if (!isCurrent()) return
      initializing = false
      await reload()
    } catch {
      if (isCurrent()) loadIssue.value = 'adventureLaunchUnavailable'
    } finally {
      if (launch === launchSequence) {
        initializing = false
        loading.value = false
      }
    }
  }
  onScopeDispose(() => { ++sequence; ++discoverySequence; ++launchSequence })
  return { adventures, catalogue, moduleId, playMode, selectedKey, availableModuleAdventures, selectedAdventure, ready, issue, loading, bindingPayload, initializeLaunch, selectPlayMode }
}
