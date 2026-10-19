<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, errorMessage } from '@/api/client'
import { useLocale } from '@/composables/useLocale'
import PlayStageHeader from '@/features/play/surface/PlayStageHeader.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { profileCopy } from './copy'
import type { ProfileView } from './types'
const props = defineProps<{ gameKey: string; initial: ProfileView }>()
const state = ref(props.initial), busy = ref(false), error = ref(''), { locale } = useLocale()
const copy = computed(() => profileCopy(locale.value)), base = computed(() => `/games/${encodeURIComponent(props.gameKey)}`)
const label = (identity: string) => copy.value[identity as keyof typeof copy.value] || identity
const has = (section: string) => state.value.profile?.ui_sections.includes(section)
const selected = computed(() => state.value.actors.find(actor => actor.uid === state.value.actor_uid))
const objective = computed(() => state.value.profile?.id === 'core:demo-heist' ? copy.value.objectiveHeist : copy.value.objectiveSurvival)
const sceneMarkers = computed(() => {
  const progression = state.value.progression
  const markers = [state.value.status]
  if (progression.mode === 'phase') markers.push(`${copy.value.phase}: ${label(progression.phase)}`)
  else markers.push(`${copy.value.day}: ${progression.day}`)
  return markers
})
async function refresh(actorUid = state.value.actor_uid) {
  state.value = await api<ProfileView>(`${base.value}/profile?actor=${encodeURIComponent(actorUid)}`)
}
async function act(type: string, moveId?: string) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const body = { type, expected_revision: state.value.revision, expected_run_id: state.value.run_id, ...(type !== 'advance' ? { actor_uid: state.value.actor_uid, expected_control_revision: state.value.control_revision, ...(moveId ? { move_id: moveId } : {}) } : {}) }
    const result = await api<{ ok: boolean; view: ProfileView }>(`${base.value}/profile/actions`, { method: 'POST', body: JSON.stringify(body) })
    state.value = result.view
  } catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
async function changeControl() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const gm = state.value.gm_uid
    await api(`${base.value}/players/${encodeURIComponent(state.value.actor_uid)}/control?user=${encodeURIComponent(gm)}`, { method: 'POST', body: JSON.stringify({ mode: state.value.control_mode === 'ai' ? 'human' : 'ai' }) })
    await refresh()
  } catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
async function reload(actorUid = state.value.actor_uid) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await refresh(actorUid) } catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}
const actorName = (uid: string) => state.value.actors.find(actor => actor.uid === uid)?.name || '—'
</script>
<template>
  <main class="profile-board view" :class="{ 'player-page': !state.is_gm }" data-testid="profile-board">
    <PlayStageHeader :title="state.game_name" :subtitle="objective" :markers="sceneMarkers" heading-tag="h1">
      <template #trailing>
        <div class="profile-header-actions">
          <RouterLink v-if="state.is_gm" :to="{ name: 'overview' }">{{ copy.back }}</RouterLink>
          <strong>{{ label(state.status) }}</strong>
          <button data-testid="profile-refresh" :disabled="busy" @click="reload()">{{ copy.refresh }}</button>
          <ThemeToggle v-if="!state.is_gm" />
        </div>
      </template>
    </PlayStageHeader>
    <section class="profile-time"><strong>{{ state.progression.mode === 'phase' ? copy.phase : copy.day }}: {{ state.progression.mode === 'phase' ? label(state.progression.phase) : state.progression.day }}</strong><span v-if="state.progression.mode === 'phase'">{{ copy.cycle }}: {{ state.progression.cycle }}</span><span v-if="state.weather">{{ copy.weather }}: {{ label(state.weather) }}</span><button v-if="state.can_advance" data-testid="profile-advance" :disabled="busy" @click="act('advance')">{{ copy.advance }}</button></section>
    <p v-if="error" role="alert">{{ error }}</p>
    <section v-if="has('resources')" class="profile-section profile-resources"><h2>{{ copy.resources }}</h2><div class="profile-meters"><article v-for="(value, key) in state.resources" :key="key"><span>{{ label(key) }}</span><strong :data-testid="`profile-resource-${key}`">{{ value }}</strong></article></div></section>
    <section v-if="has('clocks')" class="profile-section profile-clocks"><h2>{{ copy.clocks }}</h2><div class="profile-meters"><article v-for="(value, key) in state.clocks" :key="key"><span>{{ label(key) }}</span><progress :value="value" max="4" /><strong>{{ value }} / 4</strong></article></div></section>
    <section v-if="has('actors')" class="profile-section profile-actors-section"><h2>{{ copy.actors }}</h2><div class="profile-actors"><article v-for="actor in state.actors" :key="actor.uid"><h3>{{ actor.name }}</h3><div v-for="(value, key) in actor.stats || {}" :key="key">{{ label(key) }}: {{ value }}</div><p v-if="actor.health !== undefined">{{ copy.health }}: {{ actor.health }} / 5</p><p v-if="actor.stress !== undefined">{{ copy.stress }}: {{ actor.stress }} / 9 · {{ copy.harm }}: {{ actor.harm }} / 3</p><p>{{ copy.inventory }}: {{ actor.inventory.map(label).join(' · ') || '—' }}</p><RouterLink v-if="state.is_gm && actor.uid !== state.gm_uid" :to="{ name: 'play', query: { game: gameKey, user: actor.uid, share: '1' } }">{{ copy.share }}</RouterLink></article></div></section>
    <section class="profile-section profile-actions"><h2>{{ copy.actions }}</h2><select v-if="state.is_gm" :value="state.actor_uid" :disabled="busy" data-testid="profile-actor" @change="reload(($event.target as HTMLSelectElement).value)"><option v-for="actor in state.actors" :key="actor.uid" :value="actor.uid">{{ actor.name }}</option></select><p>{{ selected?.name }}</p>
      <button v-if="state.is_gm" :disabled="busy" data-testid="profile-control" @click="changeControl">{{ state.control_mode === 'ai' ? copy.restore : copy.takeover }}</button>
      <div class="profile-buttons"><button v-for="action in state.control_mode === 'human' ? state.actions : []" :key="action.id" :data-testid="`profile-move-${action.id}`" :disabled="busy" @click="act('move', action.id)">{{ label(action.id) }}</button><button v-if="state.is_gm && state.control_mode === 'ai' && state.actions.length" data-testid="profile-auto" :disabled="busy" @click="act('auto')">{{ copy.auto }}</button></div><p v-if="!state.actions.length && state.status === 'active'">{{ copy.waiting }}</p>
    </section>
    <section v-if="has('history')" class="profile-section profile-history-section"><h2>{{ copy.history }}</h2><ol class="profile-history"><li v-for="event in [...state.history].reverse()" :key="event.revision">{{ event.revision }} · {{ actorName(event.actor_uid) }} · {{ event.move_id ? label(event.move_id) : copy.advance }}<span v-if="event.roll"> · d6={{ event.roll }}</span><span v-if="event.success !== undefined"> · {{ event.success ? copy.success : copy.failure }}</span><span v-if="event.weather"> · {{ label(event.weather) }}</span><span v-if="event.shortage"> · {{ copy.shortage }}</span></li></ol></section>
  </main>
</template>
<style scoped>
.profile-board { max-width: 1100px; margin: auto; display: grid; gap: 1rem; padding: 1rem; box-sizing: border-box; } .profile-header-actions, .profile-time, .profile-buttons { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; } .profile-meters, .profile-actors { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: .75rem; } article, .profile-board>section { padding: 1rem; border: 1px solid var(--df-border-soft); border-radius: .75rem; min-width: 0; } article { display: grid; gap: .4rem; } h2, h3, p { margin: .3rem 0; } progress, select { max-width: 100%; } button { min-height: 40px; white-space: normal; } .profile-history { padding-left: 1.3rem; } .profile-board { overflow-wrap: anywhere; } .profile-section { min-width: 0; } .profile-actions, .profile-history-section { background: color-mix(in srgb, var(--df-surface, #fff) 92%, var(--df-accent, #7c3aed)); }
.player-page header { padding-top: 3rem; }
.profile-board .profile-actions,
.profile-board .profile-history-section { background: color-mix(in srgb, var(--df-surface-1) 94%, var(--df-interactive)); }
.profile-meters strong { font-size: 1.5rem; font-family: var(--df-font-title); }
.profile-board :deep(.scene-title) { font-size: clamp(1.35rem, 3vw, 2rem); }
.profile-board :deep(.scene-chips) { max-width: none; }
.profile-board {
  color: var(--df-text);
  background: var(--df-canvas, transparent);
}
.profile-board > section {
  padding: .8rem;
  background: var(--df-surface-1);
  box-shadow: 0 8px 22px rgb(0 0 0 / 5%);
}
.profile-board .profile-time {
  padding: .65rem .8rem;
  border-color: color-mix(in srgb, var(--df-accent) 32%, var(--df-border-soft));
  background: color-mix(in srgb, var(--df-surface-1) 90%, var(--df-accent));
  font-size: .86rem;
}
.profile-board .profile-time strong { color: var(--df-accent-strong, var(--df-text)); }
.profile-board .profile-section h2 {
  margin: 0 0 .65rem;
  color: var(--df-text-muted);
  font-size: .74rem;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.profile-board article { padding: .7rem; background: var(--df-surface-2, var(--df-surface-1)); }
.profile-board article h3 { font-size: .96rem; }
.profile-board .profile-buttons { gap: .5rem; }
.profile-board .profile-buttons button { flex: 1 1 150px; }
.profile-board .profile-history { margin: 0; color: var(--df-text-muted); font-size: .82rem; line-height: 1.5; }
.profile-board select { min-height: 36px; border-color: var(--df-border-soft); border-radius: var(--df-radius-sm, 8px); background: var(--df-control-bg, var(--df-surface-1)); color: var(--df-text); }
@media (max-width: 600px) {
  .profile-board { gap: .7rem; padding: .7rem; }
  .profile-board > section { padding: .7rem; }
  .profile-meters, .profile-actors { grid-template-columns: 1fr; gap: .55rem; }
  .profile-header-actions, .profile-time { align-items: stretch; gap: .5rem; }
  .profile-header-actions > *, .profile-time > button { flex: 1 1 auto; }
  .profile-buttons button { flex-basis: 100%; }
}
</style>
