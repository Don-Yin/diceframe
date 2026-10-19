import type { Locale } from '@/i18n'
import { filterByContentLanguage } from '@/utils/contentLanguage'

/** Filter the server's scoped choices, retaining only an explicitly linked
 * book when its language differs. Catalogue lookup must not replace scope. */
export function lorebookChoices<T extends { id: string; language?: unknown }>(
  books: T[], language: Locale, linkedBookId = '',
): T[] {
  const choices = filterByContentLanguage(books, language)
  const linked = linkedBookId && books.find(book => book.id === linkedBookId)
  return linked && !choices.some(book => book.id === linked.id) ? [...choices, linked] : choices
}
