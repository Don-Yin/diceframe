type AccessTokenChangeListener = () => void

const listeners = new Set<AccessTokenChangeListener>()

export function onAccessTokenChange(listener: AccessTokenChangeListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function notifyAccessTokenChange(): void {
  for (const listener of [...listeners]) listener()
}
