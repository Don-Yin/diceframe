import {
  MAX_APPLICATION_BYTES,
  encodeApplicationMessage,
  parseApplicationMessage,
  type PeerApplicationMessage,
} from '@/peer/game/protocol'

const MAX_FRAME_BYTES = 64 * 1024
const CHUNK_CHARACTERS = 12_000
const MAX_TRANSFER_CHUNKS = 192
const MAX_ACTIVE_TRANSFERS = 4
const TRANSFER_TTL_MS = 30_000

interface TransferChunk {
  version: 1
  type: 'transfer.chunk'
  transfer_id: string
  index: number
  total: number
  data: string
}

interface PendingTransfer {
  chunks: Array<string | undefined>
  received: number
  characters: number
  updatedAt: number
}

export function encodeApplicationFrames(message: PeerApplicationMessage): string[] {
  const encoded = encodeApplicationMessage(message)
  const bytes = new TextEncoder().encode(encoded).byteLength
  if (bytes > MAX_APPLICATION_BYTES) throw new Error('application_message_too_large')
  if (bytes <= MAX_FRAME_BYTES) return [encoded]
  const chunks: string[] = []
  for (let offset = 0; offset < encoded.length; offset += CHUNK_CHARACTERS) {
    chunks.push(encoded.slice(offset, offset + CHUNK_CHARACTERS))
  }
  if (chunks.length > MAX_TRANSFER_CHUNKS) throw new Error('application_message_too_large')
  return chunks.map((data, index) => JSON.stringify({
    version: 1,
    type: 'transfer.chunk',
    transfer_id: message.id,
    index,
    total: chunks.length,
    data,
  } satisfies TransferChunk))
}

export class ApplicationFrameDecoder {
  private readonly transfers = new Map<string, PendingTransfer>()

  accept(raw: string): PeerApplicationMessage | null {
    if (new TextEncoder().encode(raw).byteLength > MAX_FRAME_BYTES) {
      throw new Error('application_frame_too_large')
    }
    const candidate = decodeObject(raw)
    if (candidate.type !== 'transfer.chunk') return parseApplicationMessage(raw)
    const chunk = validateChunk(candidate)
    this.cleanup()
    let transfer = this.transfers.get(chunk.transfer_id)
    if (!transfer) {
      if (this.transfers.size >= MAX_ACTIVE_TRANSFERS) {
        throw new Error('too_many_application_transfers')
      }
      transfer = {
        chunks: Array.from({ length: chunk.total }),
        received: 0,
        characters: 0,
        updatedAt: Date.now(),
      }
      this.transfers.set(chunk.transfer_id, transfer)
    }
    if (transfer.chunks.length !== chunk.total) throw new Error('invalid_application_transfer')
    const existing = transfer.chunks[chunk.index]
    if (existing !== undefined && existing !== chunk.data) {
      this.transfers.delete(chunk.transfer_id)
      throw new Error('invalid_application_transfer')
    }
    if (existing === undefined) {
      transfer.chunks[chunk.index] = chunk.data
      transfer.received += 1
      transfer.characters += chunk.data.length
    }
    transfer.updatedAt = Date.now()
    if (transfer.characters > MAX_APPLICATION_BYTES) {
      this.transfers.delete(chunk.transfer_id)
      throw new Error('application_message_too_large')
    }
    if (transfer.received !== chunk.total) return null
    this.transfers.delete(chunk.transfer_id)
    return parseApplicationMessage(transfer.chunks.join(''))
  }

  clear(): void {
    this.transfers.clear()
  }

  private cleanup(): void {
    const cutoff = Date.now() - TRANSFER_TTL_MS
    for (const [id, transfer] of this.transfers) {
      if (transfer.updatedAt < cutoff) this.transfers.delete(id)
    }
  }
}

function decodeObject(raw: string): Record<string, unknown> {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    throw new Error('invalid_application_message')
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('invalid_application_message')
  }
  return value as Record<string, unknown>
}

function validateChunk(value: Record<string, unknown>): TransferChunk {
  if (
    value.version !== 1
    || value.type !== 'transfer.chunk'
    || typeof value.transfer_id !== 'string'
    || !value.transfer_id
    || value.transfer_id.length > 100
    || !Number.isInteger(value.index)
    || !Number.isInteger(value.total)
    || Number(value.total) < 2
    || Number(value.total) > MAX_TRANSFER_CHUNKS
    || Number(value.index) < 0
    || Number(value.index) >= Number(value.total)
    || typeof value.data !== 'string'
    || value.data.length > CHUNK_CHARACTERS
  ) {
    throw new Error('invalid_application_transfer')
  }
  return value as unknown as TransferChunk
}
