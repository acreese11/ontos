// Types mirroring the backend DQX check catalog served at
// GET /api/quality/dqx-check-catalog (see src/backend/src/common/dqx_catalog.py).
// Drives the instructive quality-check picker (Phase 2b).

export type CheckGrain = 'column' | 'object'

// Mirrors CheckArg.type in the backend catalog.
export type CheckArgType =
  | 'string'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'string[]'
  | 'column'
  | 'columns'
  | 'sql'

export interface DqxCheckArg {
  name: string
  type: CheckArgType
  required: boolean
  help?: string
  example?: unknown
  default?: unknown
}

export interface DqxCheckDef {
  function: string
  label: string
  description: string
  grain: CheckGrain
  in_v1_subset: boolean
  example: string
  // Name of the arg auto-filled with the property name when authored on a column.
  column_arg: string | null
  args: DqxCheckArg[]
}

export interface DqxCheckCatalog {
  checks: DqxCheckDef[]
  // Functions DQX derives from property constraints — the picker redirects these
  // to the Constraints tab rather than offering them.
  constraint_derived_functions: string[]
}

// The executable DQX check shape stored on a quality rule's `implementation`.
export interface DqxCheck {
  function: string
  arguments: Record<string, unknown>
}

export interface DqxImplementation {
  check: DqxCheck
  name: string
  criticality: 'error' | 'warn'
}
