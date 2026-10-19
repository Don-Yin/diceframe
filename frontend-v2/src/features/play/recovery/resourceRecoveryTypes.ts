export type RecoveryKind = 'overnight' | 'therapy' | 'luck' | 'reward'
export interface RecoveryActor {
  uid: string; name: string; eligible: boolean; reason?: string
  skills: Array<{ id: string; name: string }>
}
export interface RecoverySource {
  source_id: string; kind: RecoveryKind; actor_uid: string
  healer_uid?: string; skill_id?: string; resource_key?: string
  resource_delta?: number | string; reason?: string; origin_id?: string; started_tick?: number
  status: 'pending' | 'approved' | 'settled' | 'rejected'
}
export interface RecoveryReceipt {
  source_id: string; operation_id: string; actor_uid: string; kind: RecoveryKind
  resource_key: string; before: number; after: number; resource_delta: number
  rolls: unknown; success?: boolean; fumble?: boolean; check_id?: string; healer_uid?: string; skill_id?: string
}
export interface RecoverySnapshot {
  ok: boolean; supported: boolean; run_id: string; revision: number; is_gm: boolean
  policy: { version: number; policy: 'coc_light' | 'coc7e_style'; luck_recovery: 'check' | 'off' }
  actions: Array<{ id: 'overnight' | 'therapy'; resource_key: string; amount: string; duration_minutes: number }>
  actors: RecoveryActor[]; sources: RecoverySource[]; receipts: RecoveryReceipt[]
  intermissions: Array<{ id: string; round: number }>; blockers?: string[]; message?: string
}
export type RecoveryCommand = 'request' | 'approve' | 'reject' | 'claim' | 'reward' | 'luck'
