import type { GameDetail } from '@/api/types'

/**
 * 判断本地缓存的玩家身份 uid 是否仍是该局成员。
 *
 * 玩家加入后前端会把 uid 存进 localStorage（`trpg_play_user_<gameKey>`），
 * JoinView / PlayView 用它直接跳游玩界面。被踢、席位链接被 GM 重新生成、
 * 或者本设备没有该席位的凭证时，服务端只给访客大厅视图，此时必须走重新加入。
 *
 * 服务端在 detail.viewer 里明确告诉我们这次是按谁投影的：只有它说
 * 「你就是这个席位」才算成员。没有 viewer 的旧负载（例如旧服务端或 P2P
 * 房主转发的投影）才回退到 multiplayer 名单。
 */
export function isStoredPlayerMember(detail: GameDetail | Partial<GameDetail>, uid: string): boolean {
  if (!uid) return false
  const viewer = detail.viewer
  if (viewer) return viewer.kind === 'seat' && viewer.uid === uid
  const m = detail.multiplayer
  const members = [
    ...(m?.ready_players ?? []),
    ...(m?.waiting_players ?? []),
    ...(m?.away_players ?? []),
  ]
  return members.some(player => player.user_id === uid)
}
