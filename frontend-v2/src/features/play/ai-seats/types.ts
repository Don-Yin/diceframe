export type AISeatStyle = 'character' | 'concise' | 'cautious' | 'bold' | 'supportive'
export interface AISeatSettings { provider_ref: string | null; model: string | null; style: AISeatStyle | null }
export interface AISeatView {
  ready: boolean; reason: string; provider_ref?: string; provider_name?: string; model?: string; style?: AISeatStyle
  settings: Partial<AISeatSettings>; inherits: boolean; generating: boolean; retry_reason: string
  last_outcome: { status: string; reason: string; round: number } | null
}
export interface AISeatResponse {
  ok: boolean; revision: number; defaults: AISeatSettings; seats: Record<string, AISeatView>
  providers: Array<{ id: string; name: string; models: string[] }>; styles: AISeatStyle[]
  application?: { provider_ref: string; model: string }; combat_policy: string
}

const styles: AISeatStyle[] = ['character', 'concise', 'cautious', 'bold', 'supportive']
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function settings(value: unknown): boolean {
  return record(value) && ['provider_ref', 'model'].every(key => value[key] == null || typeof value[key] === 'string')
    && (value.style == null || styles.includes(value.style as AISeatStyle))
}

export function parseAISeatResponse(value: unknown): AISeatResponse {
  if (!record(value) || value.ok !== true || !Number.isInteger(value.revision)
    || !settings(value.defaults) || !record(value.seats) || !Array.isArray(value.providers)
    || !value.providers.every(p => record(p) && typeof p.id === 'string' && typeof p.name === 'string'
      && Array.isArray(p.models) && p.models.every(m => typeof m === 'string'))
    || !Array.isArray(value.styles) || !value.styles.every(s => styles.includes(s))
    || !Object.values(value.seats).every(s => record(s) && settings(s.settings)
      && typeof s.ready === 'boolean' && typeof s.reason === 'string'
      && typeof s.generating === 'boolean' && typeof s.retry_reason === 'string'
      && (s.style == null || styles.includes(s.style as AISeatStyle))
      && (s.last_outcome == null || (record(s.last_outcome) && typeof s.last_outcome.status === 'string'
        && typeof s.last_outcome.reason === 'string' && Number.isInteger(s.last_outcome.round))))) {
    throw new Error('Invalid AI seat response')
  }
  return value as unknown as AISeatResponse
}
