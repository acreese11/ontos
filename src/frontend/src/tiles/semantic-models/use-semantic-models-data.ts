import { useState, useEffect } from 'react';
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel } from '@/types/settings';
import { TileData } from '../types';

export function useSemanticModelsData(): TileData {
  const { hasPermission, appliedRoleId, isLoading: permissionsLoading } = usePermissions();
  const [data, setData] = useState<TileData>({
    value: 0,
    loading: true,
    error: null,
  });

  useEffect(() => {
    // Don't fetch while permissions are loading
    if (permissionsLoading) {
      return;
    }

    if (!hasPermission('semantic-models', FeatureAccessLevel.READ_ONLY)) {
      setData({
        value: 0,
        loading: false,
        error: null,
        customData: {
          modelsCount: 0,
          collectionBreakdown: [],
        },
      });
      return;
    }

    fetch('/api/semantic-models/stats')
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(apiData => {
        const modelsCount = apiData?.stats?.taxonomies?.length || 0;
        const totalTerms = (apiData?.stats?.total_concepts || 0) + (apiData?.stats?.total_properties || 0);
        const taxonomies = apiData?.stats?.taxonomies || [];

        // Calculate collection breakdown - show top 4 collections by concept count
        const collectionBreakdown = taxonomies
          .filter((t: any) => {
            // Filter out internal meta sources (urn:meta:*)
            if (t.name && t.name.startsWith('urn:meta:')) return false;
            // Filter out items without name or zero concepts
            if (!t.name || typeof t.concepts_count !== 'number' || t.concepts_count <= 0) return false;
            return true;
          })
          .map((t: any) => ({
            id: t.name, // Use name as ID for filtering
            name: t.name,
            count: t.concepts_count
          }))
          .sort((a: any, b: any) => b.count - a.count)
          .slice(0, 4);

        setData({
          value: totalTerms,
          loading: false,
          error: null,
          customData: {
            modelsCount,
            collectionBreakdown,
          },
        });
      })
      .catch(error => {
        console.error('Error fetching semantic models:', error);
        setData({
          value: 0,
          loading: false,
          error: error.message,
          customData: {
            modelsCount: 0,
            collectionBreakdown: [],
          },
        });
      });
  }, [hasPermission, appliedRoleId, permissionsLoading]);

  return data;
}
