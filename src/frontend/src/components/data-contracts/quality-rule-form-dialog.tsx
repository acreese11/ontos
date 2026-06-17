import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import type { QualityRule } from '@/types/data-contract'
import type { CheckGrain, DqxCheckArg, DqxCheckDef } from '@/types/dqx-catalog'
import { useDqxCatalog, checksForGrain } from '@/hooks/use-dqx-catalog'

type QualityRuleFormProps = {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (rule: QualityRule) => Promise<void>
  initial?: QualityRule
  // Grain of the surface this dialog is opened from. Filters the check catalog
  // and sets the emitted rule's `level`.
  grain?: CheckGrain
  // For column grain: the property this rule is attached to (auto-fills the check's
  // column argument) and the columns available for column-picker args.
  column?: string
  availableColumns?: string[]
}

const QUALITY_DIMENSIONS = ['accuracy', 'completeness', 'conformity', 'consistency', 'coverage', 'timeliness', 'uniqueness']
const QUALITY_SEVERITIES = ['info', 'warning', 'error']
const BUSINESS_IMPACTS = ['operational', 'regulatory']
// Freeform ("Other engine") authoring — for non-DQX rules. DQX is the default path.
const QUALITY_TYPES = ['text', 'library', 'sql', 'custom']
const QUALITY_LEVELS = ['contract', 'object', 'property']

// Ontos severity → DQX criticality (DQX only knows error | warn).
function mapCriticality(severity: string): 'error' | 'warn' {
  return severity === 'error' ? 'error' : 'warn'
}

// Coerce a raw form value to the type DQX expects for an argument.
function coerceArg(arg: DqxCheckArg, raw: unknown): unknown {
  if (arg.type === 'string[]' || arg.type === 'columns') {
    if (Array.isArray(raw)) return raw
    return String(raw ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
  }
  if (arg.type === 'number' || arg.type === 'integer') {
    const n = Number(raw)
    return Number.isFinite(n) ? n : undefined
  }
  if (arg.type === 'boolean') return Boolean(raw)
  return String(raw ?? '').trim()
}

function isEmptyValue(v: unknown): boolean {
  return v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0)
}

// Build the DQX check `arguments` object from the form values, omitting empty optionals.
function buildArguments(check: DqxCheckDef, values: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const arg of check.args) {
    const coerced = coerceArg(arg, values[arg.name])
    // Omit empty values: empty optionals shouldn't emit noise (e.g. no `msg: null`),
    // and missing required args are surfaced by validation in handleSubmit.
    if (isEmptyValue(coerced)) continue
    out[arg.name] = coerced
  }
  return out
}

// Readable one-liner derived from the check + arguments (mirrors backend to_display).
function toDisplay(check: DqxCheckDef, args: Record<string, unknown>, column?: string): string {
  const col = (args.column as string) || column || ''
  switch (check.function) {
    case 'sql_expression':
      return (args.expression as string)?.trim() || '(custom SQL)'
    case 'is_in_list':
      return `${col} in [${(args.allowed as string[])?.join(', ') ?? ''}]`
    case 'is_not_in_list':
      return `${col} not in [${(args.forbidden as string[])?.join(', ') ?? ''}]`
    case 'is_data_fresh':
      return `${col} fresh within ${args.max_age_minutes ?? '?'} min`
    case 'is_aggr_not_greater_than':
      return `${args.aggr_type ?? 'count'}(${col || '*'}) ≤ ${args.limit ?? '?'}`
    case 'is_unique':
      return `unique(${(args.columns as string[])?.join(', ') ?? ''})`
    case 'foreign_key':
      return `${(args.columns as string[])?.join(', ') ?? ''} → ${args.ref_table ?? '?'}`
    default:
      return `${check.label}${col ? ` on ${col}` : ''}`
  }
}

export default function QualityRuleFormDialog({
  isOpen,
  onOpenChange,
  onSubmit,
  initial,
  grain = 'object',
  column,
  availableColumns = [],
}: QualityRuleFormProps) {
  const { toast } = useToast()
  const { catalog, loading, error } = useDqxCatalog()
  const [isSubmitting, setIsSubmitting] = useState(false)

  const [fn, setFn] = useState<string>('')
  const [argValues, setArgValues] = useState<Record<string, unknown>>({})
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [dimension, setDimension] = useState('completeness')
  const [severity, setSeverity] = useState('warning')
  const [businessImpact, setBusinessImpact] = useState('operational')

  // DQX is the default/recommended path; "other" exposes the freeform fields for
  // non-DQX engines (stored + round-tripped, not run by the built-in DQX runner).
  const [mode, setMode] = useState<'dqx' | 'other'>('dqx')
  const [engine, setEngine] = useState('')
  const [ruleType, setRuleType] = useState('library')
  const [ruleText, setRuleText] = useState('')
  const [query, setQuery] = useState('')
  const [level, setLevel] = useState('object')

  const checks = useMemo(() => checksForGrain(catalog, grain), [catalog, grain])
  const selected = useMemo(() => checks.find((c) => c.function === fn) || null, [checks, fn])
  const v1 = useMemo(() => checks.filter((c) => c.in_v1_subset), [checks])
  const more = useMemo(() => checks.filter((c) => !c.in_v1_subset), [checks])

  // Recover the selected function + arguments from an existing rule's implementation
  // (the executable source of truth), so editing never strips it.
  function parseInitial(rule: QualityRule): { fn: string; args: Record<string, unknown> } | null {
    if (!rule.implementation) return null
    try {
      const impl = typeof rule.implementation === 'string' ? JSON.parse(rule.implementation) : (rule.implementation as any)
      const check = impl?.check
      if (check?.function) return { fn: check.function, args: check.arguments || {} }
    } catch {
      /* legacy / non-JSON implementation — fall through */
    }
    return null
  }

  // (Re)initialize when opened.
  useEffect(() => {
    if (!isOpen) return
    setName(initial?.name || '')
    setDescription(initial?.description || '')
    setDimension(initial?.dimension || 'completeness')
    setSeverity(initial?.severity || 'warning')
    setBusinessImpact(initial?.businessImpact || 'operational')
    // Freeform fields (other-engine path).
    setEngine(initial?.engine && initial.engine !== 'dqx' ? initial.engine : '')
    setRuleType(initial?.type || 'library')
    setRuleText(initial?.rule || '')
    setQuery(initial?.query || '')
    setLevel(initial?.level || (grain === 'column' ? 'property' : 'object'))

    const recovered = initial ? parseInitial(initial) : null
    const isOtherEngine = !!(initial?.engine && initial.engine !== 'dqx')
    const isLegacyFreeform = !!(initial && !recovered && (initial.rule || initial.query))
    if (isOtherEngine || isLegacyFreeform) {
      // Editing an existing non-DQX / legacy freeform rule → open in "Other engine".
      setMode('other')
      setFn('')
      setArgValues({})
    } else if (recovered) {
      setMode('dqx')
      setFn(recovered.fn)
      setArgValues(recovered.args)
    } else {
      setMode('dqx')
      setFn('')
      setArgValues({})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, initial])

  // Seed argument defaults + pre-fill the column arg when the chosen check changes.
  function onPickCheck(nextFn: string) {
    setFn(nextFn)
    const check = checks.find((c) => c.function === nextFn)
    if (!check) {
      setArgValues({})
      return
    }
    const seed: Record<string, unknown> = {}
    for (const arg of check.args) {
      if (arg.default !== undefined && arg.default !== null) seed[arg.name] = arg.default
    }
    if (check.column_arg && column) seed[check.column_arg] = column
    setArgValues(seed)
    if (!name.trim()) setName(`${column ? column + '_' : ''}${nextFn}`)
  }

  const previewArgs = useMemo(
    () => (selected ? buildArguments(selected, argValues) : {}),
    [selected, argValues],
  )
  const previewImpl = useMemo(() => {
    if (!selected) return null
    return {
      check: { function: selected.function, arguments: previewArgs },
      name: name.trim() || `${column ? column + '_' : ''}${selected.function}`,
      criticality: mapCriticality(severity),
    }
  }, [selected, previewArgs, name, severity, column])

  const setArg = (argName: string, value: unknown) => setArgValues((p) => ({ ...p, [argName]: value }))

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast({ title: 'Validation Error', description: 'Rule name is required', variant: 'destructive' })
      return
    }

    // Other-engine (freeform) path: emit a non-DQX rule that round-trips but isn't
    // run by the built-in DQX runner.
    if (mode === 'other') {
      if (!ruleText.trim() && !query.trim()) {
        toast({ title: 'Validation Error', description: 'Provide a rule expression or a SQL query', variant: 'destructive' })
        return
      }
      setIsSubmitting(true)
      try {
        const qualityRule: QualityRule = {
          name: name.trim(),
          description: description.trim() || undefined,
          level,
          dimension,
          businessImpact,
          severity,
          type: ruleType,
          engine: engine.trim() || undefined,
          rule: ruleText.trim() || undefined,
          query: query.trim() || undefined,
        }
        await onSubmit(qualityRule)
        onOpenChange(false)
      } catch (err: any) {
        toast({ title: 'Error', description: err?.message || 'Failed to save quality rule', variant: 'destructive' })
      } finally {
        setIsSubmitting(false)
      }
      return
    }

    if (!selected) {
      toast({ title: 'Validation Error', description: 'Pick a check', variant: 'destructive' })
      return
    }
    const missing = selected.args.filter((a) => a.required && isEmptyValue(coerceArg(a, argValues[a.name])))
    if (missing.length) {
      toast({
        title: 'Validation Error',
        description: `Missing required: ${missing.map((a) => a.name).join(', ')}`,
        variant: 'destructive',
      })
      return
    }

    setIsSubmitting(true)
    try {
      const ruleName = name.trim()
      const implementation = {
        check: { function: selected.function, arguments: previewArgs },
        name: ruleName,
        criticality: mapCriticality(severity),
      }
      const qualityRule: QualityRule = {
        name: ruleName,
        description: description.trim() || undefined,
        level: grain === 'column' ? 'property' : 'object',
        dimension,
        businessImpact,
        severity,
        type: 'custom',
        engine: 'dqx',
        rule: toDisplay(selected, previewArgs, column),
        implementation: JSON.stringify(implementation),
      }
      await onSubmit(qualityRule)
      onOpenChange(false)
    } catch (err: any) {
      toast({ title: 'Error', description: err?.message || 'Failed to save quality rule', variant: 'destructive' })
    } finally {
      setIsSubmitting(false)
    }
  }

  const renderArg = (arg: DqxCheckArg) => {
    const value = argValues[arg.name]
    const placeholder = arg.example !== undefined ? `e.g. ${Array.isArray(arg.example) ? arg.example.join(', ') : arg.example}` : ''
    const label = (
      <Label htmlFor={`arg-${arg.name}`} className="text-sm">
        {arg.name}
        {!arg.required && <span className="ml-1 text-xs text-muted-foreground">(optional)</span>}
      </Label>
    )
    let input: JSX.Element
    if (arg.type === 'boolean') {
      input = (
        <div className="flex items-center gap-2 h-9">
          <Switch id={`arg-${arg.name}`} checked={Boolean(value)} onCheckedChange={(c) => setArg(arg.name, c)} />
          <span className="text-sm text-muted-foreground">{Boolean(value) ? 'true' : 'false'}</span>
        </div>
      )
    } else if (arg.type === 'sql') {
      input = (
        <Textarea
          id={`arg-${arg.name}`}
          value={(value as string) ?? ''}
          onChange={(e) => setArg(arg.name, e.target.value)}
          placeholder={placeholder || 'a boolean SQL expression (pass = true)'}
          rows={3}
          className="font-mono text-sm"
        />
      )
    } else if (arg.type === 'column' && availableColumns.length > 0) {
      input = (
        <Select value={(value as string) || ''} onValueChange={(v) => setArg(arg.name, v)}>
          <SelectTrigger id={`arg-${arg.name}`}><SelectValue placeholder="Select column" /></SelectTrigger>
          <SelectContent>
            {availableColumns.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
      )
    } else if (arg.type === 'number' || arg.type === 'integer') {
      input = (
        <Input id={`arg-${arg.name}`} type="number" value={(value as any) ?? ''}
          onChange={(e) => setArg(arg.name, e.target.value === '' ? '' : Number(e.target.value))} placeholder={placeholder} className="h-9" />
      )
    } else {
      // string | string[] | columns | column(no list) → text. Lists are comma-separated.
      const isList = arg.type === 'string[]' || arg.type === 'columns'
      const display = Array.isArray(value) ? (value as string[]).join(', ') : ((value as string) ?? '')
      input = (
        <Input id={`arg-${arg.name}`} value={display}
          onChange={(e) => setArg(arg.name, isList ? e.target.value.split(',').map((s) => s.trim()).filter(Boolean) : e.target.value)}
          placeholder={placeholder || (isList ? 'comma-separated' : '')} className="h-9" />
      )
    }
    return (
      <div key={arg.name} className="space-y-1">
        {label}
        {input}
        {arg.help && <p className="text-xs text-muted-foreground">{arg.help}</p>}
      </div>
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initial ? 'Edit Quality Check' : 'Add Quality Check'}</DialogTitle>
          <DialogDescription>
            Author a quality check{column ? <> for <code className="text-foreground">{column}</code></> : <> for this {grain}</>}.
            DQX is the default — what you author there is exactly what DQX runs.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={mode} onValueChange={(v) => setMode(v as 'dqx' | 'other')}>
          <TabsList className="grid grid-cols-2 w-full">
            <TabsTrigger value="dqx">DQX (recommended)</TabsTrigger>
            <TabsTrigger value="other">Other engine</TabsTrigger>
          </TabsList>

          <TabsContent value="dqx">
            {loading && <p className="text-sm text-muted-foreground py-4">Loading check catalog…</p>}
            {error && <p className="text-sm text-destructive py-4">Couldn't load the check catalog: {error}</p>}

            {catalog && (
              <div className="space-y-4 py-2">
                {/* Check picker */}
            <div className="space-y-2">
              <Label htmlFor="check">Check</Label>
              <Select value={fn} onValueChange={onPickCheck}>
                <SelectTrigger id="check"><SelectValue placeholder="Choose a check…" /></SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel>Common</SelectLabel>
                    {v1.map((c) => <SelectItem key={c.function} value={c.function}>{c.label}</SelectItem>)}
                  </SelectGroup>
                  {more.length > 0 && (
                    <SelectGroup>
                      <SelectLabel>More checks</SelectLabel>
                      {more.map((c) => <SelectItem key={c.function} value={c.function}>{c.label}</SelectItem>)}
                    </SelectGroup>
                  )}
                </SelectContent>
              </Select>
              {!selected && (
                <p className="text-xs text-muted-foreground">
                  Tip: not-null, unique, pattern and range checks live on the column's <strong>Constraints</strong> tab —
                  DQX generates those automatically. This picker is for everything beyond a constraint.
                </p>
              )}
            </div>

            {/* Selected-check explainer */}
            {selected && (
              <div className="rounded-md border bg-muted/40 p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="font-mono text-xs">{selected.function}</Badge>
                  <span className="text-sm font-medium">{selected.label}</span>
                </div>
                <p className="text-sm text-muted-foreground">{selected.description}</p>
                {selected.example && <p className="text-xs text-muted-foreground">Example: <code>{selected.example}</code></p>}
              </div>
            )}

            {/* Arguments */}
            {selected && (
              <div className="grid grid-cols-2 gap-3">
                {selected.args.map(renderArg)}
              </div>
            )}

            {/* Governance metadata */}
            {selected && (
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="severity">Severity</Label>
                  <Select value={severity} onValueChange={setSeverity}>
                    <SelectTrigger id="severity"><SelectValue /></SelectTrigger>
                    <SelectContent>{QUALITY_SEVERITIES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="dimension">Dimension</Label>
                  <Select value={dimension} onValueChange={setDimension}>
                    <SelectTrigger id="dimension"><SelectValue /></SelectTrigger>
                    <SelectContent>{QUALITY_DIMENSIONS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="businessImpact">Business impact</Label>
                  <Select value={businessImpact} onValueChange={setBusinessImpact}>
                    <SelectTrigger id="businessImpact"><SelectValue /></SelectTrigger>
                    <SelectContent>{BUSINESS_IMPACTS.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {/* Name + description */}
            {selected && (
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label htmlFor="name">Name <span className="text-destructive">*</span></Label>
                  <Input id="name" value={name} onChange={(e) => setName(e.target.value)} className="h-9" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="description">Description</Label>
                  <Textarea id="description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
                </div>
              </div>
            )}

            {/* Live preview of the compiled DQX check */}
            {selected && previewImpl && (
              <div className="space-y-1">
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Runs in DQX as</Label>
                <pre className="rounded-md border bg-muted/40 p-3 text-xs overflow-x-auto font-mono">
{JSON.stringify(previewImpl, null, 2)}
                </pre>
              </div>
            )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="other">
            <div className="space-y-4 py-2">
              <p className="text-xs text-muted-foreground">
                For a non-DQX engine (soda, Great Expectations, dbt, …). The rule is stored and
                round-trips through the contract, but the built-in DQX runner doesn't execute it.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="of-name">Name <span className="text-destructive">*</span></Label>
                  <Input id="of-name" value={name} onChange={(e) => setName(e.target.value)} className="h-9" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="of-engine">Engine</Label>
                  <Input id="of-engine" value={engine} onChange={(e) => setEngine(e.target.value)} placeholder="e.g. soda, great-expectations, dbt" className="h-9" />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="of-type">Type</Label>
                  <Select value={ruleType} onValueChange={setRuleType}>
                    <SelectTrigger id="of-type"><SelectValue /></SelectTrigger>
                    <SelectContent>{QUALITY_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="of-level">Level</Label>
                  <Select value={level} onValueChange={setLevel}>
                    <SelectTrigger id="of-level"><SelectValue /></SelectTrigger>
                    <SelectContent>{QUALITY_LEVELS.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="of-severity">Severity</Label>
                  <Select value={severity} onValueChange={setSeverity}>
                    <SelectTrigger id="of-severity"><SelectValue /></SelectTrigger>
                    <SelectContent>{QUALITY_SEVERITIES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="of-dimension">Dimension</Label>
                  <Select value={dimension} onValueChange={setDimension}>
                    <SelectTrigger id="of-dimension"><SelectValue /></SelectTrigger>
                    <SelectContent>{QUALITY_DIMENSIONS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="of-bi">Business impact</Label>
                  <Select value={businessImpact} onValueChange={setBusinessImpact}>
                    <SelectTrigger id="of-bi"><SelectValue /></SelectTrigger>
                    <SelectContent>{BUSINESS_IMPACTS.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor="of-rule">Rule expression</Label>
                <Textarea id="of-rule" value={ruleText} onChange={(e) => setRuleText(e.target.value)} rows={2}
                  placeholder="engine-specific rule, e.g. col_name is not null" />
              </div>
              {ruleType === 'sql' && (
                <div className="space-y-1">
                  <Label htmlFor="of-query">SQL query</Label>
                  <Textarea id="of-query" value={query} onChange={(e) => setQuery(e.target.value)} rows={3}
                    className="font-mono text-sm" placeholder="SELECT COUNT(*) FROM … WHERE …" />
                </div>
              )}
              <div className="space-y-1">
                <Label htmlFor="of-desc">Description</Label>
                <Textarea id="of-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
              </div>
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={isSubmitting || (mode === 'dqx' && !selected)}>
            {isSubmitting ? 'Saving…' : initial ? 'Save Changes' : 'Add Check'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
