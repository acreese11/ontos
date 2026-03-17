import { useState, useEffect, useCallback, useMemo } from 'react';
import { Loader2, Trash2, AlertTriangle, Box, Table2, Eye, Columns2, Database, Shapes } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useApi } from '@/hooks/use-api';
import { useToast } from '@/hooks/use-toast';

interface DeletePreviewItem {
  id: string;
  name: string;
  asset_type_name: string | null;
  relationship_type: string | null;
  level: number;
  children: DeletePreviewItem[];
}

interface CascadeDeleteResult {
  deleted: { id: string; name: string; asset_type_name?: string }[];
  failed: { id: string; name: string; error: string }[];
}

interface AssetDeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  assetId: string;
  assetName: string;
  onDeleted: () => void;
}

const TYPE_ICONS: Record<string, React.ElementType> = {
  Table: Table2,
  View: Eye,
  Column: Columns2,
  Dataset: Database,
};

function getTypeIcon(typeName: string | null): React.ElementType {
  if (!typeName) return Box;
  return TYPE_ICONS[typeName] || Shapes;
}

function flattenTree(node: DeletePreviewItem): string[] {
  const ids = [node.id];
  for (const child of node.children) {
    ids.push(...flattenTree(child));
  }
  return ids;
}

function countNodes(node: DeletePreviewItem): number {
  let count = 1;
  for (const child of node.children) {
    count += countNodes(child);
  }
  return count;
}

export function AssetDeleteDialog({
  open,
  onOpenChange,
  assetId,
  assetName,
  onDeleted,
}: AssetDeleteDialogProps) {
  const [preview, setPreview] = useState<DeletePreviewItem | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const { get: apiGet, post: apiPost } = useApi();
  const { toast } = useToast();

  const fetchPreview = useCallback(async () => {
    if (!assetId) return;
    setIsLoadingPreview(true);
    try {
      const response = await apiGet<DeletePreviewItem>(`/api/assets/${assetId}/delete-preview`);
      if (response.error) throw new Error(response.error);
      if (response.data) {
        setPreview(response.data);
        setCheckedIds(new Set(flattenTree(response.data)));
      }
    } catch (err: any) {
      toast({ variant: 'destructive', title: 'Error', description: err.message || 'Failed to load delete preview' });
      setPreview(null);
    } finally {
      setIsLoadingPreview(false);
    }
  }, [assetId, apiGet, toast]);

  useEffect(() => {
    if (open && assetId) {
      fetchPreview();
    } else {
      setPreview(null);
      setCheckedIds(new Set());
    }
  }, [open, assetId, fetchPreview]);

  const totalCount = useMemo(() => (preview ? countNodes(preview) : 0), [preview]);
  const hasChildren = totalCount > 1;

  const toggleNode = useCallback(
    (node: DeletePreviewItem, checked: boolean) => {
      setCheckedIds((prev) => {
        const next = new Set(prev);
        const ids = flattenTree(node);
        if (checked) {
          ids.forEach((id) => next.add(id));
        } else {
          ids.forEach((id) => next.delete(id));
        }
        return next;
      });
    },
    [],
  );

  const handleDelete = async () => {
    if (checkedIds.size === 0) return;
    setIsDeleting(true);
    try {
      const response = await apiPost<CascadeDeleteResult>('/api/assets/cascade-delete', {
        asset_ids: Array.from(checkedIds),
      });
      if (response.error) throw new Error(response.error);
      const data = response.data;
      if (data) {
        if (data.deleted.length > 0) {
          toast({
            title: 'Assets deleted',
            description: `Successfully deleted ${data.deleted.length} asset(s).`,
          });
        }
        if (data.failed.length > 0) {
          toast({
            variant: 'destructive',
            title: 'Some deletions failed',
            description: `${data.failed.length} asset(s) failed to delete.`,
          });
        }
      }
      onOpenChange(false);
      onDeleted();
    } catch (err: any) {
      toast({ variant: 'destructive', title: 'Delete failed', description: err.message });
    } finally {
      setIsDeleting(false);
    }
  };

  const renderNode = (node: DeletePreviewItem, isRoot = false) => {
    const indent = node.level * 24;
    const isChecked = checkedIds.has(node.id);
    const Icon = getTypeIcon(node.asset_type_name);
    const childrenSelected = node.children.length > 0
      ? node.children.filter((c) => checkedIds.has(c.id)).length
      : 0;

    return (
      <div key={node.id}>
        <div
          className="flex items-center gap-2 py-1.5 px-2 hover:bg-muted/50 rounded-sm"
          style={{ paddingLeft: `${indent + 8}px` }}
        >
          <Checkbox
            checked={isChecked}
            disabled={isRoot}
            onCheckedChange={(checked) => toggleNode(node, !!checked)}
            className="shrink-0"
          />
          <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="text-sm truncate flex-1">{node.name}</span>
          {node.asset_type_name && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
              {node.asset_type_name}
            </Badge>
          )}
          {node.relationship_type && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 shrink-0">
              {node.relationship_type}
            </Badge>
          )}
          {node.children.length > 0 && (
            <span className="text-[10px] text-muted-foreground shrink-0">
              {childrenSelected}/{node.children.length}
            </span>
          )}
        </div>
        {node.children.map((child) => renderNode(child))}
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Trash2 className="h-5 w-5 text-destructive" />
            Delete Asset
          </DialogTitle>
          <DialogDescription>
            {hasChildren
              ? `"${assetName}" has child assets. Select which ones to delete.`
              : `Are you sure you want to delete "${assetName}"? This action cannot be undone.`}
          </DialogDescription>
        </DialogHeader>

        {isLoadingPreview ? (
          <div className="flex items-center justify-center py-8 gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-sm">Loading related assets...</span>
          </div>
        ) : preview && hasChildren ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded-md p-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>Deleting a parent asset will also delete selected children.</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {checkedIds.size} of {totalCount} asset(s) selected
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs px-2"
                  onClick={() => preview && setCheckedIds(new Set(flattenTree(preview)))}
                >
                  Select All
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs px-2"
                  onClick={() => preview && setCheckedIds(new Set([preview.id]))}
                >
                  Select None
                </Button>
              </div>
            </div>
            <div className="border rounded-md overflow-y-auto max-h-80">
              <div className="p-1">{renderNode(preview, true)}</div>
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isDeleting}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={isDeleting || isLoadingPreview || checkedIds.size === 0}
          >
            {isDeleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Delete {checkedIds.size > 1 ? `${checkedIds.size} Assets` : 'Asset'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
