interface CacheEntry<T> {
  value: T
  expiry: number
}

export class Cache {
  private static instance: Cache
  private cache = new Map<string, CacheEntry<unknown>>()
  private defaultTTL = 5000

  static getInstance(): Cache {
    if (!Cache.instance) {
      Cache.instance = new Cache()
    }
    return Cache.instance
  }

  set<T>(key: string, value: T, ttlMs?: number): void {
    this.cache.set(key, { value, expiry: Date.now() + (ttlMs ?? this.defaultTTL) })
  }

  get<T>(key: string): T | null {
    const entry = this.cache.get(key)
    if (!entry) return null
    if (Date.now() > entry.expiry) {
      this.cache.delete(key)
      return null
    }
    return entry.value as T
  }

  has(key: string): boolean {
    return this.get(key) !== null
  }

  delete(key: string): void {
    this.cache.delete(key)
  }

  clear(): void {
    this.cache.clear()
  }

  cleanup(): void {
    const now = Date.now()
    for (const [key, entry] of this.cache.entries()) {
      if (now > entry.expiry) this.cache.delete(key)
    }
  }

  getStats(): { size: number; keys: string[] } {
    this.cleanup()
    return { size: this.cache.size, keys: Array.from(this.cache.keys()) }
  }
}

export const cache = Cache.getInstance()
