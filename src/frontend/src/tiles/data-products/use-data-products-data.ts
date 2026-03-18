import { useState, useEffect } from 'react';
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel } from '@/types/settings';
import { TileData } from '../types';
import { DataProductStatus } from '@/types/data-product';

export function useDataProductsData(): TileData {
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

    if (!hasPermission('data-products', FeatureAccessLevel.READ_ONLY)) {
      setData({
        value: 0,
        loading: false,
        error: null,
        customData: {
          products: [],
          statusBreakdown: [],
        },
      });
      return;
    }

    fetch('/api/data-products')
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(apiData => {
        const productsArray = Array.isArray(apiData) ? apiData : [];

        // Calculate product status breakdown - show top 4 most-used statuses
        const statusMap = new Map<string, number>(
          Object.values(DataProductStatus).map(status => [status, 0])
        );

        // Count products by actual status
        productsArray.forEach((product: any) => {
          const status = (product.status || '').toLowerCase();
          if (statusMap.has(status)) {
            statusMap.set(status, (statusMap.get(status) || 0) + 1);
          }
        });

        // Convert to array, sort by count (descending), and take top 4
        const statusBreakdown = Array.from(statusMap.entries())
          .map(([status, count]) => ({ status, count }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 4);

        setData({
          value: productsArray.length,
          loading: false,
          error: null,
          customData: {
            products: productsArray,
            statusBreakdown,
          },
        });
      })
      .catch(error => {
        console.error('Error fetching data products:', error);
        setData({
          value: 0,
          loading: false,
          error: error.message,
          customData: {
            products: [],
            statusBreakdown: [],
          },
        });
      });
  }, [hasPermission, appliedRoleId, permissionsLoading]);

  return data;
}
