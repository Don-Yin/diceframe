<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { NIcon } from 'naive-ui'
import { GameControllerOutline } from '@vicons/ionicons5'
import type { MessageKey } from '@/i18n'
import { appNavGroups, navGroupItems, type AppNavGroupId, type AppNavItemId } from '@/navigation/appNavigation'
import { useLocale } from '@/composables/useLocale'
import { readCurrentGame } from '@/stores/gameContext'

const route = useRoute()
const { t } = useLocale()
const props = defineProps<{ groupId: AppNavGroupId }>()
const group = computed(() => appNavGroups.find(candidate => candidate.id === props.groupId)!)
const items = computed(() => navGroupItems(group.value))
const currentGame = computed(() => String(route.query.game || readCurrentGame() || ''))
const playTarget = computed(() => currentGame.value
  ? { name: 'play', query: { game: currentGame.value } }
  : { name: 'overview' })

const hintKeys: Partial<Record<AppNavItemId, MessageKey>> = {
  lorebook: 'contentWorkspaceLorebookHint',
  worlds: 'contentWorkspaceWorldsHint',
  adventures: 'contentWorkspaceAdventuresHint',
  rules: 'contentWorkspaceRulesHint',
  memory: 'sectionWorkspaceMemoryHint',
  logs: 'sectionWorkspaceLogsHint',
  plugins: 'sectionWorkspacePluginsHint',
  settings: 'sectionWorkspaceSettingsHint',
}

function hintKey(id: AppNavItemId): MessageKey {
  return hintKeys[id] || 'sectionWorkspaceDefaultHint'
}
</script>

<template>
  <div class="content-workspace" :data-workspace="groupId">
    <aside class="content-workspace-rail">
      <nav class="content-workspace-nav" :aria-label="t(group.labelKey)">
        <RouterLink
          v-for="item in items"
          :key="item.id"
          :to="{ name: item.id }"
          :class="{ active: route.name === item.id }"
        >
          <NIcon :component="item.icon" />
          <span>
            <strong>{{ t(item.labelKey) }}</strong>
            <small>{{ t(hintKey(item.id)) }}</small>
          </span>
        </RouterLink>
      </nav>

      <section v-if="groupId === 'content'" class="content-workspace-flow" :aria-label="t('contentWorkspaceRelation')">
        <span>{{ t('contentWorkspaceRelation') }}</span>
        <div>
          <b>{{ t('navLorebook') }}</b>
          <i>+</i>
          <b>{{ t('navRules') }}</b>
          <i>→</i>
          <b>{{ t('navWorlds') }}</b>
          <i>→</i>
          <b>{{ t('navAdventures') }}</b>
        </div>
        <small>{{ t('contentWorkspaceRelationHint') }}</small>
      </section>

      <footer class="content-workspace-session">
        <span>{{ currentGame ? `${t('currentTable')} ${currentGame.slice(0, 8)}` : t('lobby') }}</span>
        <RouterLink
          :to="playTarget"
          :title="t('contentWorkspaceEnterPlay')"
          :aria-label="t('contentWorkspaceEnterPlay')"
        >
          <NIcon :component="GameControllerOutline" />
          <span>{{ t('contentWorkspaceEnterPlay') }}</span>
        </RouterLink>
      </footer>
    </aside>

    <section class="content-workspace-main">
      <slot />
    </section>
  </div>
</template>
