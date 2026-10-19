export type ProfileView = {
  ok: boolean; profile: null | { id: string; version: number; title: string; ui_sections: string[] }
  game_name: string; gm_uid: string; revision: number; run_id: string; status: string; is_gm: boolean
  actor_uid: string; control_revision: number; control_mode: string
  progression: { mode: string; phase: string; cycle: number; day: number; acted: Record<string, number> }
  resources: Record<string, number>; clocks: Record<string, number>; weather?: string
  actors: Array<{ uid: string; name: string; control: { mode: string; revision: number }; stats?: Record<string, number>; stress?: number; harm?: number; health?: number; inventory: string[] }>
  actions: Array<{ id: string }>; can_advance: boolean; history: Array<{ revision: number; type: string; actor_uid: string; move_id?: string; roll?: number; success?: boolean; status?: string; weather?: string; shortage?: boolean }>
}
