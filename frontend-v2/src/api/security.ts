import { api } from '@/api/client'

export interface CertificateInfo {
  type: string
  subject: string
  issuer: string
  not_before: string
  not_after: string
  fingerprint_sha256: string
  san: string[]
  provider?: 'self_signed' | 'lets_encrypt' | string
  identifier_type?: 'dns' | 'ip' | string
  identifier?: string
  renewal_status?: string
}

export interface SecurityTransportStatus {
  ok: boolean
  tls_mode: 'off' | 'self_signed' | 'lets_encrypt'
  scheme: 'http' | 'https'
  tls_mode_source?: string
  degraded_error?: string
  certificate?: CertificateInfo
  acme?: {
    identifier_type: 'dns' | 'ip'
    identifier: string
    contact_email: string
    challenge_type: 'http-01'
    directory: 'production' | 'staging'
    certificate_profile: string
    http_challenge_port: number
  }
}

export interface SecurityPrepareResponse {
  ok: boolean
  error?: string
  mode?: string
  token?: string
  certificate?: CertificateInfo
  warnings?: string[]
}

export interface SecurityActivateResponse {
  ok: boolean
  error?: string
  tls_mode?: string
  target_scheme?: string
  target_origin?: string
  restart_required?: boolean
}

export interface SecurityRegenerateResponse {
  ok: boolean
  error?: string
  restart_required?: boolean
  previous_fingerprint?: string
  certificate?: CertificateInfo
}

export const securityApi = {
  status: () => api<SecurityTransportStatus>('/system/security/transport'),
  prepare: (mode: 'self_signed' | 'lets_encrypt', acme?: {
    identifier_type: 'dns' | 'ip'
    identifier: string
    contact_email?: string
    challenge_type?: 'http-01'
    directory?: 'production' | 'staging'
    http_challenge_port?: number
  }) =>
    api<SecurityPrepareResponse>('/system/security/transport/prepare', {
      method: 'POST',
      body: JSON.stringify({ mode, ...(acme ? { acme } : {}) }),
    }),
  activate: (token: string) =>
    api<SecurityActivateResponse>('/system/security/transport/activate', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  disable: () =>
    api<SecurityActivateResponse>('/system/security/transport/disable', { method: 'POST' }),
  regenerate: () =>
    api<SecurityRegenerateResponse>('/system/security/certificates/self-signed/regenerate', {
      method: 'POST',
    }),
}
