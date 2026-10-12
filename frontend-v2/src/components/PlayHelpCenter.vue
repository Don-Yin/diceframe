<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RuleMeta } from '@/api/types'
import { useLocale } from '@/composables/useLocale'

type HelpTab = 'current' | 'action' | 'checks' | 'combat' | 'party'

const props = withDefaults(defineProps<{
  meta?: RuleMeta | null
  isDnd?: boolean
  scene?: string
  combatStatus?: string
  campaignStatus?: string
  multiplayer?: boolean
}>(), {
  meta: null,
  isDnd: false,
  scene: '',
  combatStatus: 'none',
  campaignStatus: '',
  multiplayer: false,
})
defineEmits<{ close: [] }>()
const { locale } = useLocale()
const zh = computed(() => locale.value.startsWith('zh'))
const activeTab = ref<HelpTab>('current')

const text = (cn: string, en: string) => zh.value ? cn : en
const title = computed(() => text('游玩帮助', 'Play help'))
const tabs = computed(() => {
  const common: Array<{ id: HelpTab; label: string }> = [
    { id: 'current', label: text('当前状态', 'Current state') },
    { id: 'action', label: text('描述行动', 'Describe an action') },
    { id: 'checks', label: text('检定与结果', 'Checks & results') },
  ]
  if (props.isDnd) common.push({ id: 'combat', label: text('战斗', 'Combat') })
  if (props.multiplayer) common.push({ id: 'party', label: text('多人协作', 'Party play') })
  return common
})
const stateSummary = computed(() => {
  if (props.combatStatus === 'active') return text('战斗进行中：打开 DND5E 工具查看当前回合和合法动作。', 'Combat is active: open DND5E Tools to see the current turn and legal actions.')
  if (props.campaignStatus === 'active') return text('冒险节点进行中：剧情仍通过公共行动框推进。', 'An adventure node is active: continue through the shared action composer.')
  if (props.campaignStatus === 'completed') return text('冒险节点已完成：结果已保存，可以继续描述下一步行动。', 'The adventure node is complete: results are saved and you can describe what happens next.')
  return text('当前没有需要额外操作的状态，直接在公共行动框说出你想做的事即可。', 'Nothing needs a special control right now. Describe what you want to do in the shared action composer.')
})
const combatStatusLabel = computed(() => {
  if (props.combatStatus === 'active') return text('战斗中', 'Active')
  if (props.combatStatus === 'ended') return text('已结束', 'Ended')
  return text('未进入战斗', 'Not in combat')
})
</script>

<template>
  <div class="modal" @click.self="$emit('close')">
    <section class="dialog play-help-dialog" role="dialog" aria-modal="true" :aria-label="title">
      <header>
        <h2>{{ title }}</h2>
        <button :title="text('关闭', 'Close')" :aria-label="text('关闭', 'Close')" @click="$emit('close')">×</button>
      </header>
      <nav class="play-help-tabs" :aria-label="text('帮助主题', 'Help topics')">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >{{ tab.label }}</button>
      </nav>

      <section v-if="activeTab === 'current'" class="play-help-section">
        <p class="play-help-status">{{ stateSummary }}</p>
        <dl class="play-help-facts">
          <div><dt>{{ text('场景', 'Scene') }}</dt><dd>{{ scene || text('正在读取', 'Loading') }}</dd></div>
          <div><dt>{{ text('规则', 'Rules') }}</dt><dd>{{ String(meta?.dice_system || 'd20').toUpperCase() }}</dd></div>
          <div v-if="isDnd"><dt>{{ text('战斗状态', 'Combat') }}</dt><dd>{{ combatStatusLabel }}</dd></div>
        </dl>
        <p>{{ text('帮助内容只读，不会提交行动、推进剧情、启动战斗或改变存档。', 'Help is read-only. It never submits an action, advances the story, starts combat, or changes the save.') }}</p>
      </section>

      <section v-else-if="activeTab === 'action'" class="play-help-section">
        <h3>{{ text('把意图说清楚', 'State your intent') }}</h3>
        <p>{{ text('直接写角色想做什么、对谁做、怎么做。可以是说话、调查、移动、使用物品或攻击，不需要填写指令格式。', 'Write what your character wants to do, who they act on, and how. Talking, investigating, moving, using an item, or attacking all use the same composer.') }}</p>
        <p>{{ text('多人局中，每位玩家先提交自己的行动，系统收齐后统一处理；不要替其他玩家提交行动。', 'In multiplayer, each player submits their own action. The table resolves together after the active players have submitted.') }}</p>
      </section>

      <section v-else-if="activeTab === 'checks'" class="play-help-section">
        <h3>{{ text('什么时候会检定', 'When a check happens') }}</h3>
        <p>{{ text('只有结果不确定且会影响局势时才需要检定。系统会根据角色能力、技能熟练和场景给出骰子与难度。', 'A check is used when the outcome is uncertain and matters. The system selects the roll and difficulty from the character, skills, and scene.') }}</p>
        <p v-if="isDnd">{{ text('D&D 5E：优势掷两个 d20 取高，劣势取低；同时有优势和劣势时抵消。生命、护甲和资源由规则运行时结算。', 'D&D 5E: advantage rolls two d20s and keeps the higher result; disadvantage keeps the lower. They cancel when both apply. HP, AC, and resources are resolved by the rules runtime.') }}</p>
        <p v-else>{{ text('骰子结果和公开叙事会一起写入当前回合记录。', 'The roll and public narration are recorded together in the current round.') }}</p>
      </section>

      <section v-else-if="activeTab === 'combat'" class="play-help-section">
        <h3>{{ text('战斗怎么进行', 'How combat works') }}</h3>
        <p>{{ text('剧情确认敌对交战后，战斗工具会自动出现。先攻决定顺序，只有当前行动者可以提交动作；移动、攻击、法术、反应和伤害都由服务器校验。', 'When the story establishes hostile engagement, the combat tool appears. Initiative sets the order; only the current actor can submit an action. Movement, attacks, spells, reactions, and damage are validated by the server.') }}</p>
        <p>{{ text('敌方回合由 AI GM 按同一规则流程处理。战斗结束后回到原来的公共时间线。', 'Enemy turns are handled by the AI GM through the same rules pipeline. After combat, play returns to the same public timeline.') }}</p>
      </section>

      <section v-else class="play-help-section">
        <h3>{{ text('多人局的节奏', 'Multiplayer rhythm') }}</h3>
        <p>{{ text('普通行动会先收集全队输入再统一判定。冒险分支会显示队伍决策卡，每位玩家提交一次，GM 再按多数意见或指定分支结算。', 'Normal actions are collected from the party before one shared adjudication. Adventure branches use a party decision card: each player submits once, then the GM resolves by majority or an explicit branch.') }}</p>
        <p>{{ text('你可以随时查看队伍动态和公共时间线；不要通过工具按钮重复发送同一行动。', 'Use the party status and public timeline to follow the table. Do not resend the same action through a tool button.') }}</p>
      </section>
    </section>
  </div>
</template>

<style scoped>
.play-help-dialog{width:min(680px,100%)}
.play-help-tabs{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px;border-bottom:1px solid var(--df-border-soft);padding-bottom:8px}
.play-help-tabs button{border:1px solid var(--df-border-soft);background:var(--df-surface-1);color:var(--df-text-muted);padding:7px 10px;border-radius:6px;cursor:pointer}
.play-help-tabs button.active{border-color:var(--df-accent);color:var(--df-accent-strong);background:color-mix(in srgb,var(--df-accent) 10%,var(--df-surface-1))}
.play-help-section{padding:4px 2px;color:var(--df-text-muted);line-height:1.65}
.play-help-section h3{margin:4px 0 8px;color:var(--df-text)}
.play-help-section p{margin:8px 0}
.play-help-status{padding:11px 12px;border-left:3px solid var(--df-accent);background:color-mix(in srgb,var(--df-accent) 8%,var(--df-surface-1));color:var(--df-text)}
.play-help-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:12px 0}
.play-help-facts div{padding:9px 10px;border:1px solid var(--df-border-soft);border-radius:6px;background:var(--df-surface-1)}
.play-help-facts dt{font-size:11px;color:var(--df-text-muted)}
.play-help-facts dd{margin:3px 0 0;color:var(--df-text);font-weight:650;overflow-wrap:anywhere}
</style>
