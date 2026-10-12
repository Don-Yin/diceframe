<script setup lang="ts">
import { computed, ref } from 'vue'
import { NIcon } from 'naive-ui'
import { FlashOutline } from '@vicons/ionicons5'
import type { GameDetail } from '@/api/types'
import { useLocale } from '@/composables/useLocale'
import Modal from '@/components/ui/Modal.vue'
import CombatExtensionPanel from '@/components/play/CombatExtensionPanel.vue'

/**
 * 「战斗动作」入口：行动输入区 tools 里的按钮 + 打开既有 CombatExtensionPanel 的浮层。
 * 只有本局声明了 combat_extension 时才显示；权限逻辑仍由 CombatExtensionPanel 自己判断。
 */
const props = defineProps<{ detail: GameDetail; gameKey: string; selfUid: string; isGm: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const { t } = useLocale()

const show = ref(false)
const hasCombatExtension = computed(() => Boolean(props.detail?.combat_extension))

function open() {
  show.value = true
}
</script>

<template>
  <template v-if="hasCombatExtension">
    <button
      type="button"
      class="combat-extension-tool-trigger"
      data-testid="combat-extension-tool"
      :title="t('combatExtActionEntry')"
      :aria-label="t('combatExtActionEntry')"
      @click="open"
    ><NIcon :component="FlashOutline" /><span>{{ t('combatExtActionEntry') }}</span></button>
    <Modal v-if="show" :title="t('combatExtActionEntry')" @close="show = false">
      <CombatExtensionPanel
        :detail="detail"
        :game-key="gameKey"
        :self-uid="selfUid"
        :is-gm="isGm"
        @changed="emit('changed')"
      />
    </Modal>
  </template>
</template>

<style scoped>
.combat-extension-tool-trigger {
  white-space: nowrap;
}
</style>
