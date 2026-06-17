import { useEffect, useState } from 'react'
import { useApi } from '@/hooks/use-api'
import type { DqxCheckCatalog, DqxCheckDef, CheckGrain } from '@/types/dqx-catalog'

// The DQX check catalog is static (defined at backend import time), so cache it
// module-wide — every picker instance shares one fetch.
let _catalogCache: DqxCheckCatalog | null = null

/**
 * Fetches the DQX check catalog (GET /api/quality/dqx-check-catalog) once and
 * caches it. Drives the quality-check picker.
 */
export function useDqxCatalog() {
  const { get } = useApi()
  const [catalog, setCatalog] = useState<DqxCheckCatalog | null>(_catalogCache)
  const [loading, setLoading] = useState(!_catalogCache)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (_catalogCache) return
    let cancelled = false
    setLoading(true)
    get<DqxCheckCatalog>('/api/quality/dqx-check-catalog').then(({ data, error }) => {
      if (cancelled) return
      if (error || !data?.checks) {
        setError(error || 'Failed to load the DQX check catalog')
        setLoading(false)
        return
      }
      _catalogCache = data
      setCatalog(data)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [get])

  return { catalog, loading, error }
}

/** Checks offered for a given grain (object-grain views also get sql_expression). */
export function checksForGrain(catalog: DqxCheckCatalog | null, grain: CheckGrain): DqxCheckDef[] {
  if (!catalog) return []
  return catalog.checks.filter((c) => c.grain === grain || c.function === 'sql_expression')
}
