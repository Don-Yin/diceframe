<script setup lang="ts">
import { computed } from 'vue'
import { NIcon, NInputNumber, NSwitch } from 'naive-ui'
import { DiceOutline, FlashOutline, ChatbubbleEllipsesOutline, TrendingUpOutline } from '@vicons/ionicons5'
import type { GamePreferences, GmStyle } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import { gamePreferencesCopy } from './copy'

const props = withDefaults(defineProps<{ value: GamePreferences; scope?: 'all' | 'checks' | 'actions'; pushSupported?: boolean; quickActionsSupported?: boolean; disabled?: boolean; settingsLayout?: boolean }>(), { pushSupported: true, quickActionsSupported: true, scope: 'all' })
const emit = defineEmits<{ update: [patch: Partial<GamePreferences>] }>()
const { locale } = useLocale()
const c = computed(() => gamePreferencesCopy(locale.value))
const rowClass = computed(() => props.settingsLayout ? 'advanced-row game-preference-setting' : 'preference-row')
const groupClass = computed(() => props.settingsLayout ? 'advanced-section advanced-section-wide' : 'preference-group')
const text = (event: Event) => (event.target as HTMLInputElement).value
function style(field: keyof GmStyle, value: string) {
  emit('update', { gm_style_override: { tone: '', verbosity: 'normal', pace: 'normal', custom_instructions: '', ...props.value.gm_style_override, [field]: value } as GmStyle })
}
</script>

<template>
  <div class="game-preference-fields" :class="{ 'game-preference-settings': settingsLayout }">
    <section v-if="scope !== 'actions'" :class="groupClass">
      <header v-if="settingsLayout" class="advanced-section-head"><NIcon :component="DiceOutline" /><div><h3>{{ c.checks }}</h3><p>{{ c.checksHint }}</p></div></header>
      <fieldset :disabled="disabled">
      <legend v-if="!settingsLayout">{{ c.checks }}</legend>
      <div v-if="pushSupported !== false" :class="[rowClass, 'preference-switch']">
        <div><strong>{{ c.push }}</strong><small>{{ c.pushHint }} <template v-if="scope === 'all'">{{ c.pushScope }}</template></small></div>
        <NSwitch :value="value.push_enabled" :disabled="disabled" :aria-label="c.push" @update:value="emit('update', { push_enabled: $event })" />
      </div>
      <label :class="rowClass"><div><strong>{{ c.reveal }}</strong></div>
        <select :value="value.dice_reveal_mode" @change="emit('update', { dice_reveal_mode: text($event) as GamePreferences['dice_reveal_mode'] })">
          <option value="auto">{{ c.auto }}</option><option value="click">{{ c.click }}</option>
        </select>
      </label>
      <label :class="rowClass"><div><strong>{{ c.timeout }}</strong><small>{{ c.timeoutHint }}</small></div>
        <NInputNumber class="advanced-number" :value="value.luck_timeout_seconds" :min="0" :max="3600" :precision="0" :disabled="disabled" :input-props="{ 'aria-label': c.timeout }" @update:value="$event !== null && emit('update', { luck_timeout_seconds: $event })" />
      </label>
      </fieldset>
    </section>
    <section v-if="scope !== 'checks'" :class="groupClass">
      <header v-if="settingsLayout" class="advanced-section-head"><NIcon :component="FlashOutline" /><div><h3>{{ c.actions }}</h3><p>{{ c.actionsHint }}</p></div></header>
      <fieldset :disabled="disabled">
        <legend v-if="!settingsLayout">{{ c.actions }}</legend>
        <div :class="[rowClass, 'preference-switch']">
          <div><strong>{{ c.quickActions }}</strong><small>{{ quickActionsSupported ? c.quickActionsHint : c.quickActionsUnavailable }}</small></div>
          <NSwitch :value="value.quick_actions_enabled" :disabled="disabled || !quickActionsSupported" :aria-disabled="disabled || !quickActionsSupported" :aria-label="c.quickActions" @update:value="emit('update', { quick_actions_enabled: $event })" />
        </div>
      </fieldset>
    </section>
    <template v-if="scope === 'all'">
      <section :class="groupClass">
      <header v-if="settingsLayout" class="advanced-section-head"><NIcon :component="ChatbubbleEllipsesOutline" /><div><h3>{{ c.narration }}</h3><p>{{ c.narrationHint }}</p></div></header>
      <fieldset :disabled="disabled">
        <legend v-if="!settingsLayout">{{ c.narration }}</legend>
        <label :class="rowClass"><div><strong>{{ c.perspective }}</strong></div>
          <select :value="value.narrative_perspective" @change="emit('update', { narrative_perspective: text($event) as GamePreferences['narrative_perspective'] })">
            <option value="auto">{{ c.perspectiveAuto }}</option><option value="immersive">{{ c.immersive }}</option><option value="third_person">{{ c.third }}</option>
          </select>
        </label>
        <label :class="rowClass"><div><strong>{{ c.story }}</strong></div>
          <select :aria-label="c.story" :value="value.story_mode" @change="emit('update', { story_mode: text($event) as GamePreferences['story_mode'] })">
            <option value="prose">{{ c.prose }}</option><option value="dialogue">{{ c.dialogue }}</option>
          </select>
        </label>
        <label :class="rowClass"><div><strong>{{ c.style }}</strong></div>
          <select :value="value.gm_style_override === null ? 'world' : 'custom'" @change="emit('update', { gm_style_override: text($event) === 'world' ? null : {} })">
            <option value="world">{{ c.followWorld }}</option><option value="custom">{{ c.custom }}</option>
          </select>
        </label>
        <template v-if="value.gm_style_override !== null">
          <label :class="rowClass"><div><strong>{{ c.tone }}</strong></div>
            <select :value="value.gm_style_override.tone || ''" @change="style('tone', text($event))">
              <option value="">{{ c.neutral }}</option><option value="literary">{{ c.literary }}</option><option value="direct">{{ c.direct }}</option><option value="humorous">{{ c.humorous }}</option><option value="dark">{{ c.dark }}</option>
              <option v-if="value.gm_style_override.tone && !['literary', 'direct', 'humorous', 'dark'].includes(value.gm_style_override.tone)" :value="value.gm_style_override.tone">{{ value.gm_style_override.tone }}</option>
            </select>
          </label>
          <label :class="rowClass"><div><strong>{{ c.verbosity }}</strong></div><select :value="value.gm_style_override.verbosity || 'normal'" @change="style('verbosity', text($event))"><option value="brief">{{ c.brief }}</option><option value="normal">{{ c.normal }}</option><option value="detailed">{{ c.detailed }}</option></select></label>
          <label :class="rowClass"><div><strong>{{ c.pace }}</strong></div><select :value="value.gm_style_override.pace || 'normal'" @change="style('pace', text($event))"><option value="slow">{{ c.slow }}</option><option value="normal">{{ c.normal }}</option><option value="fast">{{ c.fast }}</option></select></label>
          <label :class="[rowClass, 'preference-notes']"><strong>{{ c.instructions }}</strong><textarea rows="3" maxlength="2000" :value="value.gm_style_override.custom_instructions || ''" @change="style('custom_instructions', text($event))" /></label>
        </template>
      </fieldset>
      </section>
      <section :class="groupClass">
      <header v-if="settingsLayout" class="advanced-section-head"><NIcon :component="TrendingUpOutline" /><div><h3>{{ c.growth }}</h3><p>{{ c.growthHint }}</p></div></header>
      <fieldset :disabled="disabled">
        <legend v-if="!settingsLayout">{{ c.growth }}</legend><p v-if="!settingsLayout" class="preference-hint">{{ c.growthHint }}</p>
        <label :class="rowClass"><div><strong>{{ c.mode }}</strong></div><select :value="value.advancement_mode" @change="emit('update', { advancement_mode: text($event) as GamePreferences['advancement_mode'] })"><option value="milestone">{{ c.milestone }}</option><option value="xp">{{ c.xp }}</option></select></label>
        <label :class="rowClass"><div><strong>{{ c.authority }}</strong></div><select :value="value.advancement_authority" @change="emit('update', { advancement_authority: text($event) as GamePreferences['advancement_authority'] })"><option value="ai_gm">{{ c.aiGm }}</option><option value="gm">{{ c.gm }}</option></select></label>
      </fieldset>
      <slot name="footer" />
      </section>
    </template>
  </div>
</template>

<style scoped>
.game-preference-fields { display: grid; gap: 22px; min-width: 0; }
.game-preference-settings { gap: 16px; }
.preference-group { min-width: 0; }
fieldset { display: grid; gap: 14px; min-width: 0; margin: 0; padding: 0; border: 0; }
.game-preference-settings fieldset { display: block; }
legend { padding: 0 0 12px; color: var(--df-accent-strong); font-weight: 700; }
.preference-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(100px, 180px); gap: 14px; align-items: center; margin: 0; }
.preference-switch { grid-template-columns: minmax(0, 1fr) auto; }
.preference-row strong, .preference-notes strong { font-size: 13px; }
.preference-row small, .preference-hint { display: block; margin: 5px 0 0; color: var(--df-text-muted); font-size: 12px; line-height: 1.6; }
.preference-hint { margin: 0; }
.preference-row select, .preference-row input { box-sizing: border-box; width: 100%; min-width: 0; margin: 0; }
.preference-row :deep(.n-input-number) { min-width: 0; width: 100%; }
.game-preference-setting > select { width: min(260px, 100%); min-width: 0; justify-self: end; }
.preference-notes { display: grid; gap: 8px; margin: 0; }
.game-preference-setting.preference-notes { grid-template-columns: minmax(0, 1fr); }
.preference-notes textarea { width: 100%; min-width: 0; box-sizing: border-box; }
@media(max-width: 560px) { .game-preference-setting > select { width: 100%; justify-self: stretch; } }
</style>
