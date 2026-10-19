import type { AssistantAvatarMood } from '@/components/assistant/AssistantAvatar.vue'

/*
 * Catalogue of table events the DF Agent avatar reacts to. Producers report a
 * kind (and an optional detail such as an amount or a name); this table owns
 * how each kind looks, how long it lasts and how important it is.
 */

export type AssistantReactionCategory = 'check' | 'combat' | 'story' | 'growth' | 'table'

export type AssistantReactionKind =
  | 'diceRoll' | 'critical' | 'success' | 'failure' | 'fumble'
  | 'combatStart' | 'combatEnd' | 'yourTurn' | 'attackCrit' | 'attackHit' | 'attackMiss'
  | 'hurt' | 'heal' | 'downed' | 'deathSave'
  | 'newRound' | 'sceneChange' | 'sceneImage' | 'gameEnded'
  | 'levelUp' | 'xpGain' | 'itemGain' | 'hpLow'
  | 'playerJoin' | 'playerLeave' | 'pushOffered'

export interface AssistantReactionDetail { amount?: number; name?: string }

interface ReactionSpec {
  category: AssistantReactionCategory
  mood: AssistantAvatarMood
  /** Higher wins when two reactions arrive together. */
  priority: number
  durationMs: number
  label: (zh: boolean, detail: AssistantReactionDetail) => string
  tone?: 'good' | 'bad' | 'great'
}

const named = (detail: AssistantReactionDetail, zh: boolean) => detail.name ? (zh ? `：${detail.name}` : `: ${detail.name}`) : ''
const amount = (detail: AssistantReactionDetail) => Math.abs(Number(detail.amount || 0))

export const ASSISTANT_REACTIONS: Record<AssistantReactionKind, ReactionSpec> = {
  diceRoll: { category: 'check', mood: 'rolling', priority: 10, durationMs: 1400, label: zh => zh ? '掷骰中…' : 'Rolling…' },
  critical: { category: 'check', mood: 'cheer', priority: 80, durationMs: 3200, tone: 'great', label: zh => zh ? '大成功！' : 'Critical success!' },
  success: { category: 'check', mood: 'nod', priority: 50, durationMs: 2200, tone: 'good', label: zh => zh ? '成功' : 'Success' },
  failure: { category: 'check', mood: 'sad', priority: 50, durationMs: 2400, tone: 'bad', label: zh => zh ? '失败…' : 'Failed…' },
  fumble: { category: 'check', mood: 'dizzy', priority: 80, durationMs: 3200, tone: 'bad', label: zh => zh ? '大失败！' : 'Fumble!' },

  combatStart: { category: 'combat', mood: 'battle', priority: 70, durationMs: 2800, tone: 'bad', label: zh => zh ? '进入战斗！' : 'Combat begins!' },
  combatEnd: { category: 'combat', mood: 'happy', priority: 70, durationMs: 2800, tone: 'good', label: zh => zh ? '战斗结束' : 'Combat over' },
  yourTurn: { category: 'combat', mood: 'alert', priority: 75, durationMs: 3000, label: zh => zh ? '轮到你了！' : 'Your turn!' },
  attackCrit: { category: 'combat', mood: 'cheer', priority: 80, durationMs: 3000, tone: 'great', label: zh => zh ? '暴击！' : 'Critical hit!' },
  attackHit: { category: 'combat', mood: 'nod', priority: 55, durationMs: 2000, tone: 'good', label: zh => zh ? '命中！' : 'Hit!' },
  attackMiss: { category: 'combat', mood: 'sad', priority: 45, durationMs: 2000, tone: 'bad', label: zh => zh ? '落空了' : 'Missed' },
  hurt: { category: 'combat', mood: 'hurt', priority: 65, durationMs: 2400, tone: 'bad', label: (zh, d) => amount(d) ? `-${amount(d)} HP` : (zh ? '受伤了' : 'Ouch') },
  heal: { category: 'combat', mood: 'happy', priority: 55, durationMs: 2200, tone: 'good', label: (zh, d) => amount(d) ? `+${amount(d)} HP` : (zh ? '恢复了' : 'Healed') },
  downed: { category: 'combat', mood: 'dizzy', priority: 90, durationMs: 3600, tone: 'bad', label: zh => zh ? '倒下了！' : 'Down!' },
  deathSave: { category: 'combat', mood: 'worried', priority: 85, durationMs: 3000, tone: 'bad', label: zh => zh ? '死亡豁免…撑住！' : 'Death save… hold on!' },

  newRound: { category: 'story', mood: 'curious', priority: 20, durationMs: 1800, label: (zh, d) => zh ? `第 ${d.amount ?? ''} 轮` : `Round ${d.amount ?? ''}` },
  sceneChange: { category: 'story', mood: 'curious', priority: 40, durationMs: 2800, label: (zh, d) => (zh ? '新场景' : 'New scene') + named(d, zh) },
  sceneImage: { category: 'story', mood: 'surprised', priority: 30, durationMs: 2200, label: zh => zh ? '场景图来了' : 'Scene art is ready' },
  gameEnded: { category: 'story', mood: 'cheer', priority: 90, durationMs: 3600, tone: 'great', label: zh => zh ? '冒险结束，辛苦了！' : 'Adventure complete!' },

  levelUp: { category: 'growth', mood: 'cheer', priority: 85, durationMs: 3400, tone: 'great', label: (zh, d) => zh ? `升级！Lv.${d.amount ?? ''}` : `Level up! Lv.${d.amount ?? ''}` },
  xpGain: { category: 'growth', mood: 'nod', priority: 35, durationMs: 2200, tone: 'good', label: (zh, d) => zh ? `+${amount(d)} 经验` : `+${amount(d)} XP` },
  itemGain: { category: 'growth', mood: 'happy', priority: 40, durationMs: 2600, tone: 'good', label: (zh, d) => (zh ? '获得物品' : 'New item') + named(d, zh) },
  hpLow: { category: 'growth', mood: 'worried', priority: 70, durationMs: 3000, tone: 'bad', label: zh => zh ? '生命值告急！' : 'HP is low!' },

  playerJoin: { category: 'table', mood: 'happy', priority: 30, durationMs: 2400, label: (zh, d) => (zh ? '新伙伴加入' : 'A player joined') + named(d, zh) },
  playerLeave: { category: 'table', mood: 'sad', priority: 25, durationMs: 2200, label: (zh, d) => (zh ? '有人离开了' : 'A player left') + named(d, zh) },
  pushOffered: { category: 'table', mood: 'worried', priority: 60, durationMs: 3000, label: zh => zh ? '要孤注一掷吗？' : 'Push your luck?' },
}

export const ASSISTANT_REACTION_CATEGORIES: AssistantReactionCategory[] = ['check', 'combat', 'story', 'growth', 'table']

export function assistantReactionCategoryCopy(locale: string): Record<AssistantReactionCategory, { label: string; hint: string }> {
  return locale.startsWith('zh') ? {
    check: { label: '检定', hint: '掷骰、大成功、成功、失败、大失败' },
    combat: { label: '战斗', hint: '开战、轮到你、命中/暴击/落空、受伤/治疗、倒地、死亡豁免' },
    story: { label: '剧情', hint: '新一轮、新场景、场景图、冒险结束' },
    growth: { label: '成长', hint: '升级、经验、获得物品、生命值告急' },
    table: { label: '同桌', hint: '玩家加入/离开、孤注一掷' },
  } : {
    check: { label: 'Checks', hint: 'Rolling, critical, success, failure, fumble' },
    combat: { label: 'Combat', hint: 'Start, your turn, hit/crit/miss, damage/healing, downed, death saves' },
    story: { label: 'Story', hint: 'New round, new scene, scene art, adventure complete' },
    growth: { label: 'Growth', hint: 'Level up, XP, items gained, low HP' },
    table: { label: 'Table', hint: 'Players joining/leaving, push your luck' },
  }
}
