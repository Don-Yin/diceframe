class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>()

  get length() {
    return this.values.size
  }

  clear() {
    this.values.clear()
  }

  getItem(key: string) {
    return this.values.get(String(key)) ?? null
  }

  key(index: number) {
    return Array.from(this.values.keys())[index] ?? null
  }

  removeItem(key: string) {
    this.values.delete(String(key))
  }

  setItem(key: string, value: string) {
    this.values.set(String(key), String(value))
  }
}

// Node 26 exposes an incomplete experimental localStorage when no backing file is
// configured. Pin tests to a deterministic in-memory implementation instead of
// depending on the Node process or jsdom's origin-specific storage behavior.
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: new MemoryStorage(),
})
