/**
 * Minimum length for a room password being set now. The server enforces the
 * same rules; passwords set before the minimum was raised keep working.
 */
export const ROOM_PASSWORD_MIN_LENGTH = 6

export type RoomPasswordProblem = 'blank' | 'too_short'

/**
 * Why a new room password would be refused, or null. '' means "no password"
 * and is fine. Passwords are never trimmed anywhere (create, change or join):
 * what the GM types is exactly what players type, so a whitespace-only value
 * is refused instead of silently becoming empty.
 */
export function roomPasswordProblem(password: string): RoomPasswordProblem | null {
  const value = String(password ?? '')
  if (!value) return null
  if (!value.trim()) return 'blank'
  // Count code points like the server does, not UTF-16 units.
  return [...value].length < ROOM_PASSWORD_MIN_LENGTH ? 'too_short' : null
}

/** Whether a non-empty new room password is too short. */
export function isRoomPasswordTooShort(password: string): boolean {
  return roomPasswordProblem(password) === 'too_short'
}

/** i18n key + params describing a refused new room password. */
export function roomPasswordProblemMessage(
  problem: RoomPasswordProblem,
): ['roomPasswordBlank' | 'roomPasswordTooShort', Record<string, number>] {
  return problem === 'blank'
    ? ['roomPasswordBlank', {}]
    : ['roomPasswordTooShort', { min: ROOM_PASSWORD_MIN_LENGTH }]
}
