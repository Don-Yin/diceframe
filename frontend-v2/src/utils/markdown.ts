import { marked } from 'marked'
import DOMPurify from 'dompurify'

export function renderSafeMarkdown(markdown: string): string {
  const raw = marked.parse(markdown || '', { async: false }) as string
  return DOMPurify.sanitize(raw)
}
