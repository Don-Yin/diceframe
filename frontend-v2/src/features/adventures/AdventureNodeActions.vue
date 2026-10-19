<script setup lang="ts">
import { computed } from 'vue'
import { useLocale } from '@/composables/useLocale'
import { choiceCopy } from './choiceCopy'
type Node = { id: string; choice_mode?: string; transitions?: Array<{ choice_id?: string; choice_label?: string }> }
const props = defineProps<{ node: Node; isGm: boolean; active: boolean; busy: boolean; requests?: Array<{ node_id: string; choice_id: string; actor_uid: string }>; selected?: string }>()
const emit = defineEmits<{ submit: [choiceId?: string] }>()
const { locale, t } = useLocale(), copy = computed(() => choiceCopy(locale.value))
const proposals = computed(() => props.requests?.filter(request => request.node_id === props.node.id) || [])
const label = (choiceId: string) => props.node.transitions?.find(transition => transition.choice_id === choiceId)?.choice_label || choiceId
</script>
<template>
  <section class="node-actions">
    <template v-if="node.choice_mode === 'exclusive'">
      <p v-if="selected">{{ copy.selected }}: {{ label(selected) }}</p>
      <template v-if="active">
        <button v-for="option in node.transitions || []" :key="option.choice_id" class="primary" type="button" :data-testid="`adventure-choice-${node.id}-${option.choice_id}`" :disabled="busy" @click="emit('submit', option.choice_id)">{{ isGm ? copy.confirm : copy.request }}: {{ option.choice_label }}</button>
        <p v-if="proposals.length">{{ isGm ? copy.requests : copy.pending }}</p>
        <p v-for="proposal in isGm ? proposals : []" :key="proposal.actor_uid">{{ proposal.actor_uid }}: {{ label(proposal.choice_id) }}</p>
      </template>
    </template>
    <button v-else-if="isGm && active" class="primary" type="button" :data-testid="`adventure-complete-${node.id}`" :disabled="busy" @click="emit('submit')">{{ t('adventureCompleteNode') }}</button>
  </section>
</template>
<style scoped>
.node-actions { display: grid; gap: .5rem; justify-items: start; } button { white-space: normal; overflow-wrap: anywhere; max-width: 100%; min-height: 36px; } p { margin: 0; overflow-wrap: anywhere; }
</style>
