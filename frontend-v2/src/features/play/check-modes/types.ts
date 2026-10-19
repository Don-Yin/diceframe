export type CheckMode = 'advantage' | 'disadvantage'
export interface ModeEntry { mode: CheckMode; reason: string; status: string; decision_reason?: string }
export interface ModeSource { code: string; mode: CheckMode; reason?: string }
export interface ModeSeat { uid: string; name: string; kind: string; scope: string; context_id: string; blocked_reason: string;
  request: ModeEntry | null; grant: ModeEntry | null; previews: { label: string; mode: CheckMode | ''; sources: ModeSource[] }[] }
export interface ModeResponse { ok: true; revision: number; run_id: string; is_gm: boolean; seats: ModeSeat[] }

export function parseModeResponse(raw: unknown): ModeResponse {
  const obj = raw as Partial<ModeResponse> | null
  if (!obj || obj.ok !== true || !Number.isInteger(obj.revision) || typeof obj.run_id !== 'string'
      || typeof obj.is_gm !== 'boolean' || !Array.isArray(obj.seats)
      || obj.seats.some(s => !s || typeof s.uid !== 'string' || typeof s.name !== 'string'
        || typeof s.kind !== 'string' || typeof s.scope !== 'string' || typeof s.context_id !== 'string'
        || typeof s.blocked_reason !== 'string' || !Array.isArray(s.previews)
        || [s.request, s.grant].some(e => e !== null && (!e || !['advantage', 'disadvantage'].includes(e.mode) || typeof e.reason !== 'string' || typeof e.status !== 'string'))
        || s.previews.some(p => !p || typeof p.label !== 'string' || !['', 'advantage', 'disadvantage'].includes(p.mode)
          || !Array.isArray(p.sources) || p.sources.some(r => !r || typeof r.code !== 'string' || !['advantage', 'disadvantage'].includes(r.mode))))) {
    throw new Error('Invalid check mode response')
  }
  return obj as ModeResponse
}
