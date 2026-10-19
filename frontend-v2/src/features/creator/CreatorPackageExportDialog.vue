<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, apiBlob, errorMessage } from '@/api/client'
import Modal from '@/components/ui/Modal.vue'
import { useLocale } from '@/composables/useLocale'
import type { AdventuresResponse, RuleSummary, RulesResponse, WorldListResponse, WorldSummary } from '@/api/types'

type Book = { id: string; name?: string; entry_count?: number }
const emit = defineEmits<{ close: [] }>()
const { locale } = useLocale()
const name = ref(''), packId = ref(''), version = ref('0.1.0'), description = ref('')
const worlds = ref<WorldSummary[]>([]), adventures = ref<AdventuresResponse['adventures']>([]), books = ref<Book[]>([]), rules = ref<RuleSummary[]>([])
const selectedWorld = ref(''), selectedRule = ref(''), selectedAdventures = ref<string[]>([]), selectedBooks = ref<string[]>([])
const busy = ref(false), loading = ref(true), error = ref('')
const copy = computed(() => String(locale.value).startsWith('zh') ? {
  title: '导出自制内容包', intro: '选择要分享的内容。导出的是数据包，安装后仍需在内容来源里启用；冒险包会保留原生规则和剧情文件。', basic: '包信息', id: '包 ID', name: '名称', version: '版本', description: '说明', choose: '选择内容', world: '世界（可选）', rule: '规则（可选）', adventures: '冒险包（可多选）', books: '资料册（可多选）', export: '导出 .dfplugin', close: '取消', loading: '正在读取可导出的内容…', empty: '没有可导出的内容', required: '至少选择一个世界、冒险包或资料册。', done: '已下载内容包', locale: 'zh-CN', entries: '条目',
} : {
  title: 'Export my content pack', intro: 'Choose what to share. The export is data-only; enable it after installation in Content sources. Adventure bundles keep their native rules and story files.', basic: 'Package details', id: 'Package ID', name: 'Name', version: 'Version', description: 'Description', choose: 'Choose content', world: 'World (optional)', rule: 'Ruleset (optional)', adventures: 'Adventure packages', books: 'Lorebooks', export: 'Export .dfplugin', close: 'Cancel', loading: 'Loading exportable content…', empty: 'Nothing to export yet', required: 'Choose at least one world, adventure, or lorebook.', done: 'Content pack downloaded', locale: 'en', entries: 'entries',
})

function adventureSelectionValue(item: AdventuresResponse['adventures'][number]): string {
  return JSON.stringify([item.source_kind || (item.custom ? 'user' : 'builtin'), item.source_id || '', item.adventure_id])
}

function selectedAdventureRefs(): Array<{ adventure_id: string; source_kind: string; source_id: string }> {
  return selectedAdventures.value.flatMap(value => {
    try {
      const [source_kind, source_id, adventure_id] = JSON.parse(value) as unknown[]
      if (typeof adventure_id !== 'string' || !adventure_id.trim()) return []
      return [{ adventure_id, source_kind: typeof source_kind === 'string' ? source_kind : '', source_id: typeof source_id === 'string' ? source_id : '' }]
    } catch { return [] }
  })
}

onMounted(async () => {
  try {
    const [w, a, b, r] = await Promise.all([
      api<WorldListResponse>('/worlds'),
      api<AdventuresResponse>(`/adventures?language=${encodeURIComponent(locale.value)}`),
      api<{ books?: Book[] }>('/lorebooks?scope=all'),
      api<RulesResponse>(`/rules?language=${encodeURIComponent(locale.value)}`),
    ])
    worlds.value = w.worlds || []; adventures.value = a.adventures || []; books.value = b.books || []; rules.value = r.rules || []
  } catch (cause) { error.value = errorMessage(cause) } finally { loading.value = false }
})

async function exportPack() {
  if (!packId.value.trim() || !name.value.trim()) { error.value = copy.value.required; return }
  if (!/^[a-z0-9]+(?:[-_][a-z0-9]+)*$/.test(packId.value.trim())) { error.value = 'ID must use lowercase letters, numbers, hyphens, or underscores.'; return }
  if (!selectedWorld.value && !selectedRule.value && !selectedAdventures.value.length && !selectedBooks.value.length) { error.value = copy.value.required; return }
  busy.value = true; error.value = ''
  try {
    const response = await apiBlob('/plugins/export', { method: 'POST', body: JSON.stringify({
      plugin_id: packId.value.trim(), name: name.value.trim(), version: version.value.trim() || '0.1.0', description: description.value.trim(),
      world_id: selectedWorld.value, rule_id: selectedRule.value, adventure_ids: [], adventure_refs: selectedAdventureRefs(), lorebook_ids: selectedBooks.value, language: copy.value.locale,
    }) })
    const blob = await response.blob(), url = URL.createObjectURL(blob), anchor = document.createElement('a')
    anchor.href = url; anchor.download = `${packId.value.trim()}-${version.value.trim() || '0.1.0'}.dfplugin`; anchor.click(); URL.revokeObjectURL(url)
    emit('close')
  } catch (cause) { error.value = errorMessage(cause) } finally { busy.value = false }
}
</script>

<template>
  <Modal :title="copy.title" dialog-class="creator-package-dialog" @close="emit('close')">
    <p class="creator-package-intro">{{ copy.intro }}</p>
    <p v-if="loading" role="status">{{ copy.loading }}</p>
    <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
    <template v-if="!loading">
      <section class="creator-package-section"><h3>{{ copy.basic }}</h3><div class="creator-package-grid">
        <label><span>{{ copy.id }}</span><input v-model="packId" placeholder="my-adventure-pack"></label>
        <label><span>{{ copy.name }}</span><input v-model="name"></label>
        <label><span>{{ copy.version }}</span><input v-model="version"></label>
        <label class="wide"><span>{{ copy.description }}</span><textarea v-model="description" rows="2"></textarea></label>
      </div></section>
      <section class="creator-package-section"><h3>{{ copy.choose }}</h3><div class="creator-package-grid">
        <label><span>{{ copy.world }}</span><select v-model="selectedWorld"><option value="">—</option><option v-for="item in worlds" :key="String(item.id || item.world_id)" :value="String(item.id || item.world_id)">{{ item.name || item.world_name || item.id }}</option></select></label>
        <label><span>{{ copy.rule }}</span><select v-model="selectedRule"><option value="">—</option><option v-for="item in rules" :key="item.rule_id" :value="item.rule_id">{{ item.rule_name || item.rule_id }}</option></select></label>
        <fieldset class="wide"><legend>{{ copy.adventures }}</legend><label v-for="item in adventures" :key="adventureSelectionValue(item)" class="creator-package-check"><input v-model="selectedAdventures" type="checkbox" :value="adventureSelectionValue(item)"><span>{{ item.name || item.adventure_id }} <small>{{ item.source_id || item.source_kind }}</small></span></label><small v-if="!adventures.length">{{ copy.empty }}</small></fieldset>
        <fieldset class="wide"><legend>{{ copy.books }}</legend><label v-for="item in books" :key="item.id" class="creator-package-check"><input v-model="selectedBooks" type="checkbox" :value="item.id"><span>{{ item.name || item.id }} <small v-if="item.entry_count !== undefined">{{ item.entry_count }} {{ copy.entries }}</small></span></label><small v-if="!books.length">{{ copy.empty }}</small></fieldset>
      </div></section>
      <footer class="creator-package-actions"><button type="button" @click="emit('close')">{{ copy.close }}</button><button type="button" class="primary" :disabled="busy" @click="exportPack">{{ busy ? '…' : copy.export }}</button></footer>
    </template>
  </Modal>
</template>

<style scoped>
.creator-package-intro{margin:0;color:var(--df-text-secondary);line-height:1.5}.creator-package-section{display:grid;gap:.8rem;padding:.9rem 0;border-bottom:1px solid var(--df-border-soft)}.creator-package-section h3{margin:0;color:var(--df-accent-strong);font-size:.95rem}.creator-package-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem}.creator-package-grid label,.creator-package-grid fieldset{display:grid;gap:.35rem;min-width:0}.creator-package-grid .wide{grid-column:1/-1}.creator-package-grid input,.creator-package-grid select,.creator-package-grid textarea{box-sizing:border-box;width:100%;min-width:0;padding:.55rem;border:1px solid var(--df-border-soft);border-radius:var(--df-radius-sm);background:var(--df-control-bg);color:var(--df-text)}fieldset{border:1px solid var(--df-border-soft);border-radius:var(--df-radius-sm);padding:.65rem}.creator-package-check{display:flex!important;align-items:center;gap:.45rem}.creator-package-check input{width:auto}.creator-package-check small{color:var(--df-text-muted)}.creator-package-actions{display:flex;justify-content:flex-end;gap:.6rem;padding-top:1rem}@media(max-width:620px){.creator-package-grid{grid-template-columns:1fr}}
</style>
