import { useState, useEffect } from 'react';
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel } from '@/types/settings';
import { TileData } from '../types';

export function useDataContractsData(): TileData {
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

    if (!hasPermission('data-contracts', FeatureAccessLevel.READ_ONLY)) {
      setData({
        value: 0,
        loading: false,
        error: null,
        customData: {
          contracts: [],
          statusBreakdown: [],
        },
      });
      return;
    }

    fetch('/api/data-contracts')
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(apiData => {
        const contractsArray = Array.isArray(apiData) ? apiData : [];

        // Calculate contract status breakdown - show actual unique statuses
        const statusMap = new Map<string, number>([
          ['active', 0],
          ['draft', 0],
          ['deprecated', 0],
          ['retired', 0]
        ]);

        // Count contracts by actual status
        contractsArray.forEach((contract: any) => {
          const status = (contract.status || '').toLowerCase();
          if (statusMap.has(status)) {
            statusMap.set(status, (statusMap.get(status) || 0) + 1);
          }
        });

        // Return in fixed order: active, draft, deprecated, retired
        const statusBreakdown = [
          { status: 'active', count: statusMap.get('active') || 0 },
          { status: 'draft', count: statusMap.get('draft') || 0 },
          { status: 'deprecated', count: statusMap.get('deprecated') || 0 },
          { status: 'retired', count: statusMap.get('retired') || 0 }
        ];

        setData({
          value: contractsArray.length,
          loading: false,
          error: null,
          customData: {
            contracts: contractsArray,
            statusBreakdown,
          },
        });
      })
      .catch(error => {
        console.error('Error fetching data contracts:', error);
        setData({
          value: 0,
          loading: false,
          error: error.message,
          customData: {
            contracts: [],
            statusBreakdown: [],
          },
        });
      });
  }, [hasPermission, appliedRoleId, permissionsLoading]);

  return data;
}
