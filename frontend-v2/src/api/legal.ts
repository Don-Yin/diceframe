import { api } from '@/api/client'

export type LegalDocumentName = 'terms' | 'privacy'

export interface LegalDocumentResponse {
  ok: boolean
  document: LegalDocumentName
  language: 'zh' | 'en'
  version: string
  updated_at: string
  sha256: string
  source: 'online' | 'bundled'
  content: string
}

export function fetchLegalDocument(document: LegalDocumentName, language: string) {
  return api<LegalDocumentResponse>(
    `/legal/${document}?lang=${encodeURIComponent(language)}`,
  )
}
