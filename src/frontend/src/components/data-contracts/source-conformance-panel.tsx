import React, { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '@/components/ui/table'
import { Loader2, RefreshCcw, CheckCircle2, AlertTriangle } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'
import { useApi } from '@/hooks/use-api'
import { usePermissions } from '@/stores/permissions-store'
import { FeatureAccessLevel } from '@/types/settings'

interface ValidationResult {
  id: string
  check_type: string
  passed: boolean
  message?: string | null
  details?: {
    kind?: string
    object?: string
    column?: string
    physical_name?: string
    declared_type?: string | null
    live_type?: string | null
    declared_required?: boolean
    live_required?: boolean
  } | null
  created_at?: string | null
}

interface ValidationRun {
  id: string
  contract_id: string
  status: string
  started_at?: string | null
  finished_at?: string | null
  checks_passed: number
  checks_failed: number
  score: number
  error_message?: string | null
  results: ValidationResult[]
}

interface Props {
  contractId: string
}

function fmtDate(iso?: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

const DRIFT_LABELS: Record<string, string> = {
  missing_column: 'Missing column',
  extra_column: 'Extra column',
  type_change: 'Type change',
  nullability_change: 'Nullability change',
}

const SourceConformancePanel: React.FC<Props> = ({ contractId }) => {
  const { toast } = useToast()
  const { post, get } = useApi()
  const { hasPermission, isLoading: permissionsLoading } = usePermissions()
  const canValidate = !permissionsLoading && hasPermission('data-contracts', FeatureAccessLevel.READ_WRITE)

  const [run, setRun] = useState<ValidationRun | null>(null)
  const [loading, setLoading] = useState(false)
  const [validating, setValidating] = useState(false)

  const fetchLatest = useCallback(async () => {
    if (!contractId) return
    setLoading(true)
    const { data, error } = await get<ValidationRun | null>(`/api/data-contracts/${contractId}/validation-runs`)
    if (error) {
      // A never-validated contract is fine; only surface real errors.
      console.warn('Failed to load validation runs:', error)
    } else {
      setRun(data ?? null)
    }
    setLoading(false)
  }, [contractId, get])

  useEffect(() => {
    fetchLatest()
  }, [fetchLatest])

  const handleValidate = useCallback(async () => {
    if (!contractId) return
    setValidating(true)
    const { data, error } = await post<ValidationRun>(`/api/data-contracts/${contractId}/validate-source`, {})
    setValidating(false)
    if (error || !data) {
      toast({ title: 'Validation failed', description: error || 'Unknown error', variant: 'destructive' })
      return
    }
    setRun(data)
    if (data.checks_failed > 0) {
      toast({
        title: 'Schema drift detected',
        description: `${data.checks_failed} drift finding(s). Owner and subscribers notified.`,
        variant: 'destructive',
      })
    } else {
      toast({ title: 'Source conformance passed', description: 'Schema matches the live source.' })
    }
  }, [contractId, post, toast])

  const findings = (run?.results || []).filter((r) => !r.passed)
  const passedCount = run?.checks_passed ?? 0

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              Source Conformance
              {run && (run.checks_failed > 0 ? (
                <Badge variant="destructive" className="gap-1"><AlertTriangle className="h-3 w-3" /> Drift</Badge>
              ) : (
                <Badge variant="outline" className="gap-1 text-green-600 border-green-600"><CheckCircle2 className="h-3 w-3" /> In sync</Badge>
              ))}
            </CardTitle>
            <CardDescription>
              Validate the contract's declared schema against the live Unity Catalog source (column-level drift).
            </CardDescription>
          </div>
          <Button size="sm" onClick={handleValidate} disabled={validating || !canValidate}>
            {validating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <RefreshCcw className="h-4 w-4 mr-2" />}
            Validate against source
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center py-6"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : !run ? (
          <p className="text-sm text-muted-foreground py-2">
            This contract has not been validated against its source yet.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-6 text-sm">
              <div>
                <div className="text-muted-foreground">Status</div>
                <div className="font-medium">{run.status}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Score</div>
                <div className="font-medium">{run.score}%</div>
              </div>
              <div>
                <div className="text-muted-foreground">Checks</div>
                <div className="font-medium">{passedCount} passed / {run.checks_failed} failed</div>
              </div>
              <div>
                <div className="text-muted-foreground">Last run</div>
                <div className="font-medium">{fmtDate(run.finished_at || run.started_at)}</div>
              </div>
            </div>

            {run.error_message && (
              <p className="text-sm text-destructive">{run.error_message}</p>
            )}

            {findings.length === 0 ? (
              <p className="text-sm text-green-600 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4" /> No schema drift — the contract matches the live source.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Drift</TableHead>
                    <TableHead>Column</TableHead>
                    <TableHead>Detail</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {findings.map((f) => {
                    const d = f.details || {}
                    const kind = d.kind || 'unknown'
                    let detail = f.message || ''
                    if (kind === 'type_change') {
                      detail = `${d.declared_type ?? '?'} → ${d.live_type ?? '?'}`
                    } else if (kind === 'nullability_change') {
                      detail = `${d.declared_required ? 'required' : 'nullable'} → ${d.live_required ? 'required' : 'nullable'}`
                    } else if (kind === 'missing_column') {
                      detail = `Declared in contract, absent in table (${d.physical_name ?? ''})`
                    } else if (kind === 'extra_column') {
                      detail = `Present in table, not in contract (${d.physical_name ?? ''})`
                    }
                    return (
                      <TableRow key={f.id}>
                        <TableCell>
                          <Badge variant="outline">{DRIFT_LABELS[kind] || kind}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{d.column || '—'}</TableCell>
                        <TableCell className="text-sm">{detail}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default SourceConformancePanel
