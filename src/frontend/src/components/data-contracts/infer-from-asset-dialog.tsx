import { useState, useCallback, useEffect, useRef } from 'react';
import {
  Search, Loader2, Database, Table2, Eye, FolderOpen, Library,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useApi } from '@/hooks/use-api';
import { cn } from '@/lib/utils';

interface AssetResult {
  id: string;
  name: string;
  description?: string;
  asset_type_name?: string;
  location?: string;
  status?: string;
}

export interface InferredSchemaObject {
  name: string;
  physicalName: string;
  description: string;
  physicalType: string;
  properties: Array<{
    name: string;
    physicalType: string;
    logicalType: string;
    required: boolean;
    description: string;
    partitioned: boolean;
  }>;
}

interface InferFromAssetDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onInfer: (schemas: InferredSchemaObject[]) => void;
}

const ASSET_TYPE_ICONS: Record<string, React.ElementType> = {
  Dataset: Database,
  Table: Table2,
  View: Eye,
  Schema: FolderOpen,
  Catalog: Library,
};

const TARGET_ASSET_TYPES = ['Dataset', 'Table', 'View', 'Schema', 'Catalog'];

function getIcon(typeName?: string) {
  if (!typeName) return Database;
  return ASSET_TYPE_ICONS[typeName] || Database;
}

export default function InferFromAssetDialog({
  isOpen,
  onOpenChange,
  onInfer,
}: InferFromAssetDialogProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState<AssetResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<AssetResult | null>(null);
  const [isInferring, setIsInferring] = useState(false);
  const { get: apiGet } = useApi();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const doSearch = useCallback(async (query: string) => {
    if (query.length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const typeParam = TARGET_ASSET_TYPES.join(',');
      const url = `/api/assets?name=${encodeURIComponent(query)}&limit=30&asset_type_names=${encodeURIComponent(typeParam)}`;
      const response = await apiGet<any>(url);
      if (!response.error && response.data) {
        const items = Array.isArray(response.data)
          ? response.data
          : response.data.items || [];
        setResults(items);
      } else {
        setResults([]);
      }
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [apiGet]);

  const handleQueryChange = (value: string) => {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  };

  const handleSelect = (asset: AssetResult) => {
    setSelected(prev => prev?.id === asset.id ? null : asset);
  };

  const handleInfer = async () => {
    if (!selected) return;
    setIsInferring(true);
    try {
      const resp = await fetch(`/api/assets/${selected.id}/infer-schema`);
      if (!resp.ok) throw new Error('Failed to infer schema');
      const schemas: InferredSchemaObject[] = await resp.json();
      if (schemas.length > 0) {
        onInfer(schemas);
        onOpenChange(false);
      }
    } finally {
      setIsInferring(false);
    }
  };

  const resetState = () => {
    setSearchQuery('');
    setResults([]);
    setSelected(null);
  };

  useEffect(() => {
    if (isOpen) {
      resetState();
      setTimeout(() => searchInputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { onOpenChange(open); if (!open) resetState(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Infer Schema from Asset</DialogTitle>
          <DialogDescription>
            Search for an existing asset (Dataset, Table, View, Schema, or Catalog) and import its structure as contract schemas.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              ref={searchInputRef}
              placeholder="Search assets by name..."
              value={searchQuery}
              onChange={(e) => handleQueryChange(e.target.value)}
              className="pl-9"
            />
            {loading && (
              <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
            )}
          </div>

          <div className="flex gap-1.5 flex-wrap">
            {TARGET_ASSET_TYPES.map(t => {
              const Icon = getIcon(t);
              return (
                <Badge key={t} variant="outline" className="gap-1 text-xs">
                  <Icon className="h-3 w-3" />
                  {t}
                </Badge>
              );
            })}
          </div>

          <ScrollArea className="max-h-72">
            {results.length === 0 && searchQuery.length >= 2 && !loading && (
              <p className="text-sm text-muted-foreground text-center py-6">No matching assets found</p>
            )}
            {results.length === 0 && searchQuery.length < 2 && !loading && (
              <p className="text-sm text-muted-foreground text-center py-6">
                Type at least 2 characters to search
              </p>
            )}
            {results.length > 0 && (
              <div className="space-y-0.5">
                {results.map(asset => {
                  const isSelected = selected?.id === asset.id;
                  const Icon = getIcon(asset.asset_type_name);
                  return (
                    <button
                      key={asset.id}
                      onClick={() => handleSelect(asset)}
                      className={cn(
                        'w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors',
                        isSelected ? 'bg-primary/10 border border-primary/20' : 'hover:bg-muted'
                      )}
                    >
                      <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{asset.name}</div>
                        {asset.location && (
                          <div className="text-xs text-muted-foreground truncate">{asset.location}</div>
                        )}
                      </div>
                      <Badge variant="outline" className="text-xs flex-shrink-0">
                        {asset.asset_type_name || 'Asset'}
                      </Badge>
                    </button>
                  );
                })}
              </div>
            )}
          </ScrollArea>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleInfer} disabled={!selected || isInferring}>
            {isInferring && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Infer Schema
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
