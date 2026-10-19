<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { NIcon } from 'naive-ui'
import { GameControllerOutline } from '@vicons/ionicons5'
import type { MessageKey } from '@/i18n'
import { appNavGroups, isNavItemActive, navGroupItems, playContextQuery, type AppNavGroupId, type AppNavItemId } from '@/navigation/appNavigation'
import { useLocale } from '@/composables/useLocale'
import { readCurrentGame } from '@/stores/gameContext'
import { experienceCopy } from '@/navigation/experienceCopy'
import { libraryCopy } from '@/features/library/copy'
import { useSectionHeaderOffset } from './useSectionHeaderOffset'

const route = useRoute()
const navigationRail = ref<HTMLElement | null>(null)
const headerOffset = useSectionHeaderOffset(navigationRail)
const { locale, t } = useLocale()
const copy = computed(() => experienceCopy(locale.value))
function label(id: AppNavItemId) {
  if (id === 'lorebook') return copy.value.world
  if (id === 'modules') return libraryCopy(locale.value).sources
  if (id === 'adventures') return copy.value.author
  return t(items.value.find(item => item.id === id)!.labelKey)
}
const props = defineProps<{ groupId: AppNavGroupId }>()
const group = computed(() => appNavGroups.find(candidate => candidate.id === props.groupId)!)
const items = computed(() => navGroupItems(group.value))
const currentGame = computed(() => String(route.query.game || readCurrentGame() || ''))
const playTarget = computed(() => {
  const query = playContextQuery(route.query, currentGame.value)
  return query ? { name: 'play', query } : { name: 'overview' }
})

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
  <div class="content-workspace" :data-workspace="groupId" :style="headerOffset">
    <aside ref="navigationRail" class="content-workspace-rail">
      <nav class="content-workspace-nav" :aria-label="t(group.labelKey)">
        <RouterLink
          v-for="item in items"
          :key="item.id"
          :to="{ name: item.id }"
          :class="{ active: isNavItemActive(item.id, String(route.name || '')) }"
        >
          <NIcon :component="item.icon" />
          <span>
            <strong>{{ label(item.id) }}</strong>
            <small v-if="groupId !== 'content'">{{ t(hintKey(item.id)) }}</small>
          </span>
        </RouterLink>
      </nav>

      <footer class="content-workspace-session">
        <span>{{ currentGame ? `${t('currentTable')} ${currentGame.slice(0, 8)}` : t('lobby') }}</span>
        <RouterLink
          v-if="groupId !== 'management'"
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
