import { useEffect, useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import SearchBar from '@/components/ui/search-bar';
import { Card, CardContent, CardTitle, CardHeader, CardDescription } from '@/components/ui/card';
import { Loader2, Database, TrendingUp, FileText as FileTextIcon, Network, Scale, Globe, AlertCircle } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { UnityCatalogLogo } from '@/components/unity-catalog-logo';
import { FeatureMaturity } from '@/config/features';
import { useFeatureVisibilityStore } from '@/stores/feature-visibility-store';
import { usePermissions } from '@/stores/permissions-store';
import { FeatureAccessLevel, HomeSection } from '@/types/settings';
import { Alert, AlertDescription } from "@/components/ui/alert";
import DiscoverySection from '@/components/home/discovery-section';
import DataCurationSection from '@/components/home/data-curation-section';
import RequiredActionsSection from '@/components/home/required-actions-section';
import RequestRoleSection from '@/components/home/request-role-section';
import QuickActions from '@/components/home/quick-actions';
import RecentActivity from '@/components/home/recent-activity';
import { useUserStore } from '@/stores/user-store';
import ComplianceTrendMini from '@/components/home/compliance-trend-mini';
import ContractStatusBreakdown from '@/components/home/contract-status-breakdown';
import CollectionBreakdown from '@/components/home/collection-breakdown';
import type { DataContractListItem } from '@/types/data-contract';
import { DataProductStatus } from '@/types/data-product';

interface Stats {
  dataContracts: { count: number; loading: boolean; error: string | null };
  dataProducts: { count: number; loading: boolean; error: string | null };
  ontologies: {
    count: {
      models: number;
      totalTerms: number;
    };
    taxonomies: any[];
    loading: boolean;
    error: string | null
  };
  personas: { count: number; loading: boolean; error: string | null };
  estates: {
    count: number;
    loading: boolean;
    error: string | null;
    lastSync: string | null;
    syncStatus: 'success' | 'failed' | 'in_progress' | 'unknown' | null;
  };
}

interface ComplianceData {
  date: string;
  compliance: number;
}

export default function Home() {
  const { t, i18n } = useTranslation(['home', 'common']);
  const [stats, setStats] = useState<Stats>({
    dataContracts: { count: 0, loading: true, error: null },
    dataProducts: { count: 0, loading: true, error: null },
    ontologies: { count: { models: 0, totalTerms: 0 }, taxonomies: [], loading: true, error: null },
    personas: { count: 0, loading: true, error: null },
    estates: {
      count: 0,
      loading: true,
      error: null,
      lastSync: null,
      syncStatus: null
    },
  });
  const [complianceData, setComplianceData] = useState<ComplianceData[]>([]);
  const [complianceLoading, setComplianceLoading] = useState(true);
  const [complianceError, setComplianceError] = useState<string | null>(null);
  const [contracts, setContracts] = useState<DataContractListItem[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const allowedMaturities = useFeatureVisibilityStore((state) => state.allowedMaturities);
  const { permissions, isLoading: permissionsLoading, hasPermission, requestableRoles, appliedRoleId } = usePermissions();

  useEffect(() => {
    fetch('/api/data-products')
      .then(response => {
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
        })
      .then(data => {
        const productsArray = Array.isArray(data) ? data : [];
        setProducts(productsArray);
        setStats(prev => ({
          ...prev,
          dataProducts: { count: productsArray.length, loading: false, error: null }
        }));
      })
      .catch(error => {
        console.error('Error fetching data products:', error);
        setProducts([]);
        setStats(prev => ({
          ...prev,
          dataProducts: { count: 0, loading: false, error: error.message }
        }));
      });

    fetch('/api/data-contracts')
       .then(response => {
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
        })
      .then(data => {
        const contractsArray = Array.isArray(data) ? data : [];
        setContracts(contractsArray);
        setStats(prev => ({
          ...prev,
          dataContracts: { count: contractsArray.length, loading: false, error: null }
        }));
      })
      .catch(error => {
        console.error('Error fetching data contracts:', error);
        setContracts([]);
        setStats(prev => ({
          ...prev,
          dataContracts: { count: 0, loading: false, error: error.message }
        }));
      });

    fetch('/api/semantic-models/stats')
       .then(response => {
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
        })
      .then(data => {
        const modelsCount = data?.stats?.taxonomies?.length || 0;
        const totalTerms = (data?.stats?.total_concepts || 0) + (data?.stats?.total_properties || 0);
        const taxonomies = data?.stats?.taxonomies || [];

        setStats(prev => ({
          ...prev,
          ontologies: {
            count: {
              models: modelsCount,
              totalTerms: totalTerms
            },
            taxonomies: taxonomies,
            loading: false,
            error: null
          }
        }));
      })
      .catch(error => {
        console.error('Error fetching ontologies:', error);
        setStats(prev => ({
          ...prev,
          ontologies: {
            count: { models: 0, totalTerms: 0 },
            taxonomies: [],
            loading: false,
            error: error.message
          }
        }));
      });

    fetch('/api/entitlements/personas')
      .then(response => {
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
        })
      .then(data => {
        setStats(prev => ({
          ...prev,
          personas: { count: Array.isArray(data) ? data.length : 0, loading: false, error: null }
        }));
      })
      .catch(error => {
        console.error('Error fetching personas:', error);
        setStats(prev => ({
          ...prev,
          personas: { count: 0, loading: false, error: error.message }
        }));
      });

    fetch('/api/estates')
       .then(response => {
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
        })
      .then(data => {
        const estatesArray = Array.isArray(data) ? data : [];
        const lastSync = estatesArray.length > 0 && estatesArray.some(e => e.last_sync)
          ? new Date(Math.max(...estatesArray.filter(e => e.last_sync).map((estate: any) => new Date(estate.last_sync).getTime())))
          : null;

        let syncStatus: Stats['estates']['syncStatus'] = null;
        if (estatesArray.length > 0) {
            if (estatesArray.some((estate: any) => estate.sync_status === 'in_progress')) {
                syncStatus = 'in_progress';
            } else if (estatesArray.some((estate: any) => estate.sync_status === 'failed')) {
                syncStatus = 'failed';
            } else if (estatesArray.every((estate: any) => estate.sync_status === 'success')) {
                syncStatus = 'success';
            } else {
                syncStatus = 'unknown';
            }
        }

        setStats(prev => ({
          ...prev,
          estates: {
            count: estatesArray.length,
            loading: false,
            error: null,
            lastSync: lastSync?.toLocaleDateString() || null,
            syncStatus
          }
        }));
      })
      .catch(error => {
        console.error('Error fetching estates:', error);
        setStats(prev => ({
          ...prev,
          estates: {
            count: 0,
            loading: false,
            error: error.message,
            lastSync: null,
            syncStatus: null
          }
        }));
      });

    fetch('/api/compliance/trend')
       .then(response => {
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
        })
      .then(data => {
        setComplianceData(Array.isArray(data) ? data : []);
        setComplianceLoading(false);
      })
      .catch(error => {
        console.error('Error fetching compliance trend:', error);
        setComplianceError(error.message);
        setComplianceLoading(false);
      });
  }, []);

  const baseSummaryTiles = useMemo(() => [
    {
      id: 'semantic-models',
      title: t('home:overview.tiles.semanticModels.title'),
      value: stats.ontologies.count.totalTerms,
      loading: stats.ontologies.loading,
      error: stats.ontologies.error,
      link: '/semantic-models',
      icon: <Network className="h-4 w-4" />,
      description: t('home:overview.tiles.semanticModels.description'),
       maturity: 'ga',
    },
    {
      id: 'data-products',
      title: t('home:overview.tiles.dataProducts.title'),
      value: stats.dataProducts.count,
      loading: stats.dataProducts.loading,
      error: stats.dataProducts.error,
      link: '/data-products',
      icon: <Database className="h-4 w-4" />,
      description: t('home:overview.tiles.dataProducts.description'),
      maturity: 'ga',
    },
    {
      id: 'data-contracts',
      title: t('home:overview.tiles.dataContracts.title'),
      value: stats.dataContracts.count,
      loading: stats.dataContracts.loading,
      error: stats.dataContracts.error,
      link: '/data-contracts',
      icon: <FileTextIcon className="h-4 w-4" />,
      description: t('home:overview.tiles.dataContracts.description'),
      maturity: 'ga',
    },
    {
      id: 'compliance',
      title: t('home:overview.tiles.compliance.title'),
      value: complianceData.length > 0 ? `${complianceData[complianceData.length - 1].compliance}%` : t('home:overview.tiles.compliance.notAvailable'),
      loading: complianceLoading,
      error: complianceError,
      link: '/compliance',
      icon: <Scale className="h-4 w-4" />,
      description: t('home:overview.tiles.compliance.description'),
      maturity: 'ga',
    },
    {
      id: 'estate-manager',
      title: t('home:overview.tiles.estates.title'),
      value: stats.estates.count,
      loading: stats.estates.loading,
      error: stats.estates.error,
      link: '/estate-manager',
      icon: <Globe className="h-4 w-4" />,
      description: stats.estates.lastSync
        ? t('home:overview.tiles.estates.lastSync', {
            date: stats.estates.lastSync,
            status: t(`home:overview.tiles.estates.syncStatus.${stats.estates.syncStatus || 'unknown'}`)
          })
        : t('home:overview.tiles.estates.description'),
      maturity: 'ga',
    },
  ], [t, complianceData, complianceLoading, complianceError, stats]);

  const filteredSummaryTiles = useMemo(() => {
      if (permissionsLoading) return [];
      return baseSummaryTiles.filter(tile =>
          allowedMaturities.includes(tile.maturity as FeatureMaturity) &&
          hasPermission(tile.id, FeatureAccessLevel.READ_ONLY)
      );
  }, [baseSummaryTiles, allowedMaturities, permissionsLoading, hasPermission, appliedRoleId]);

  const isComplianceVisible = filteredSummaryTiles.some(tile => tile.id === 'compliance');

  // Calculate contract status breakdown - show actual unique statuses
  const contractStatusBreakdown = useMemo(() => {
    // Initialize with all known contract statuses (from API)
    const statusMap = new Map<string, number>([
      ['active', 0],
      ['draft', 0],
      ['deprecated', 0],
      ['retired', 0]
    ]);

    // Count contracts by actual status
    contracts.forEach(contract => {
      const status = (contract.status || '').toLowerCase();
      if (statusMap.has(status)) {
        statusMap.set(status, (statusMap.get(status) || 0) + 1);
      }
    });

    // Return in fixed order: active, draft, deprecated, retired
    return [
      { status: 'active', count: statusMap.get('active') || 0 },
      { status: 'draft', count: statusMap.get('draft') || 0 },
      { status: 'deprecated', count: statusMap.get('deprecated') || 0 },
      { status: 'retired', count: statusMap.get('retired') || 0 }
    ];
  }, [contracts]);

  // Calculate product status breakdown - show top 4 most-used statuses
  const productStatusBreakdown = useMemo(() => {
    // Initialize with all possible product statuses set to 0
    const statusMap = new Map<string, number>(
      Object.values(DataProductStatus).map(status => [status, 0])
    );

    // Count products by actual status
    products.forEach(product => {
      const status = (product.status || '').toLowerCase();
      if (statusMap.has(status)) {
        statusMap.set(status, (statusMap.get(status) || 0) + 1);
      }
    });

    // Convert to array, sort by count (descending), and take top 4
    return Array.from(statusMap.entries())
      .map(([status, count]) => ({ status, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 4);
  }, [products]);

  // Calculate collection breakdown - show top 4 collections by concept count
  const collectionBreakdown = useMemo(() => {
    const taxonomies = stats.ontologies.taxonomies || [];
    return taxonomies
      .filter(t => {
        // Filter out internal meta sources (urn:meta:*)
        if (t.name && t.name.startsWith('urn:meta:')) return false;
        // Filter out items without name or zero concepts
        if (!t.name || typeof t.concepts_count !== 'number' || t.concepts_count <= 0) return false;
        return true;
      })
      .map(t => ({
        id: t.name, // Use name as ID for filtering
        name: t.name,
        count: t.concepts_count
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 4);
  }, [stats.ontologies.taxonomies]);

  const hasAnyAccess = useMemo(() => {
      if (permissionsLoading || !permissions) return false;
      return Object.values(permissions).some(level => level !== FeatureAccessLevel.NONE);
  }, [permissions, permissionsLoading]);

  const { availableRoles } = usePermissions();
  const { userInfo } = useUserStore();
  const userGroups = (userInfo as any)?.groups || [];

  const configuredSections: HomeSection[] = useMemo(() => {
    if (appliedRoleId) {
      const r = availableRoles.find(role => role.id === appliedRoleId);
      return (r?.home_sections || []) as HomeSection[];
    }
    if (Array.isArray(userGroups) && userGroups.length > 0) {
      const groupSet = new Set<string>(userGroups as string[]);
      const matched = availableRoles.filter(r => Array.isArray(r.assigned_groups) && r.assigned_groups.some(g => groupSet.has(g)));
      const union = new Set<HomeSection>();
      matched.forEach(r => (r.home_sections || []).forEach(s => union.add(s as HomeSection)));
      const order: HomeSection[] = [HomeSection.REQUIRED_ACTIONS, HomeSection.DATA_CURATION, HomeSection.DISCOVERY];
      const result = order.filter(s => union.has(s));
      return result.length > 0 ? result : [HomeSection.DISCOVERY];
    }
    return [];
  }, [availableRoles, appliedRoleId, userGroups]);

  const defaultSections: HomeSection[] = [HomeSection.DISCOVERY];
  const orderedSections = configuredSections.length > 0 ? configuredSections : defaultSections;

  return (
    <div className="container mx-auto px-4 py-8">
      {hasAnyAccess && (
        <>
          <div className="max-w-2xl mx-auto text-center mb-8">
            <div className="flex items-center justify-center mb-4">
              <UnityCatalogLogo className="h-16 w-16" />
              <h1 className="text-4xl font-bold ml-2">
                {t('home:title')}
              </h1>
            </div>
            <p className="text-lg text-muted-foreground mb-6">
              {t('home:tagline')}
            </p>
            <div className="mb-8">
              <SearchBar
                variant="large"
                placeholder={t('home:search.placeholder')}
              />
            </div>
          </div>

          {/* Overview Tiles */}
          <div className="mb-8">
            <h2 className="text-2xl font-semibold mb-4">{t('home:overview.title')}</h2>
            {permissionsLoading ? (
              <div className="flex justify-center items-center h-24 col-span-full">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : filteredSummaryTiles.length > 0 ? (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                {filteredSummaryTiles.map((tile) => (
                  <Card key={tile.title} className="transition-colors h-full">
                    <CardContent className="p-6 flex flex-col justify-between h-full">
                      <div>
                        {/* Icon, Title, and Value in one row */}
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            <div className="h-4 w-4 text-muted-foreground flex-shrink-0">
                              {tile.icon}
                            </div>
                            <CardTitle className="text-base font-medium">
                              <Link to={tile.link} className="hover:underline">
                                {tile.title}
                              </Link>
                            </CardTitle>
                          </div>
                          <div className="flex-shrink-0">
                            {tile.loading ? (
                              <Loader2 className="h-5 w-5 animate-spin text-primary" />
                            ) : tile.error ? (
                              <span className="text-xs text-destructive">Error</span>
                            ) : (
                              <Link
                                to={tile.link}
                                className="text-3xl font-bold hover:underline"
                              >
                                {tile.value}
                              </Link>
                            )}
                          </div>
                        </div>

                          {/* Description below */}
                          <p className="text-xs text-muted-foreground mt-1">
                            {tile.description}
                          </p>

                          {/* Embed compact chart in Compliance tile */}
                          {tile.id === 'compliance' && !tile.loading && !tile.error && (
                            <div className="-mx-2" style={{ marginTop: '0.5rem' }}>
                              <ComplianceTrendMini
                                data={complianceData.length > 0 ? complianceData.map(d => d.compliance) : undefined}
                              />
                            </div>
                          )}

                          {/* Embed status breakdown in Data Contracts tile */}
                          {tile.id === 'data-contracts' && !tile.loading && !tile.error && (
                            <ContractStatusBreakdown statusCounts={contractStatusBreakdown} />
                          )}

                          {/* Embed status breakdown in Data Products tile */}
                          {tile.id === 'data-products' && !tile.loading && !tile.error && (
                            <ContractStatusBreakdown statusCounts={productStatusBreakdown} />
                          )}

                          {/* Embed collection breakdown in Semantic Models tile */}
                          {tile.id === 'semantic-models' && !tile.loading && !tile.error && (
                            <CollectionBreakdown collections={collectionBreakdown} />
                          )}
                        </div>
                      </CardContent>
                    </Card>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-center col-span-full">
                {t('home:overview.noData')}
              </p>
            )}
          </div>

          {/* Compliance Trend - Now embedded in tile above */}
          {false && isComplianceVisible && (
            <div className="mb-8">
              <Card>
                <CardHeader>
                  <div className="flex items-center space-x-4">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <TrendingUp className="h-6 w-6 text-primary" />
                    </div>
                    <div>
                      <CardTitle>{t('home:complianceTrend.title')}</CardTitle>
                      <CardDescription>{t('home:complianceTrend.period')}</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="p-6 pt-0">
                  <div className="h-[200px]">
                    {complianceLoading ? (
                      <div className="flex items-center justify-center h-full">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                      </div>
                    ) : complianceError ? (
                      <div className="flex items-center justify-center h-full text-destructive">
                        {t('home:complianceTrend.error', { error: complianceError })}
                      </div>
                    ) : complianceData.length === 0 ? (
                      <div className="flex items-center justify-center h-full text-muted-foreground">
                        {t('home:complianceTrend.noData')}
                      </div>
                    ) : (
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={complianceData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis
                            dataKey="date"
                            tickFormatter={(date) => new Date(date).toLocaleDateString(i18n.language, { month: 'short', day: 'numeric' })}
                            axisLine={false}
                            tickLine={false}
                            style={{ fontSize: '0.75rem' }}
                          />
                          <YAxis
                            domain={[0, 100]}
                            tickFormatter={(value) => `${value}%`}
                            axisLine={false}
                            tickLine={false}
                            style={{ fontSize: '0.75rem' }}
                            width={50}
                          />
                          <Tooltip
                            contentStyle={{ fontSize: '0.875rem', borderRadius: '0.5rem', boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)' }}
                            labelFormatter={(label) => new Date(label).toLocaleDateString(i18n.language, { year: 'numeric', month: 'long', day: 'numeric' })}
                            formatter={(value: number) => [`${value}%`, t('home:complianceTrend.chartLabel')]}
                          />
                          <Line
                            type="monotone"
                            dataKey="compliance"
                            stroke="hsl(var(--primary))"
                            strokeWidth={2}
                            dot={false}
                            activeDot={{ r: 6, fill: 'hsl(var(--primary))' }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Role-based sections */}
          {orderedSections.map(section => (
            section === HomeSection.REQUIRED_ACTIONS ? (
              <RequiredActionsSection key={section} />
            ) : section === HomeSection.DATA_CURATION ? (
              <DataCurationSection key={section} />
            ) : (
              <DiscoverySection key={section} />
            )
          ))}

          {/* Quick Actions and Recent Activity */}
          <section className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <QuickActions />
            <RecentActivity />
          </section>
        </>
      )}

      {/* Request Role Section */}
      {!permissionsLoading && !hasAnyAccess && requestableRoles && requestableRoles.length > 0 && (
        <div className="mb-8">
          <RequestRoleSection />
        </div>
      )}

      {/* No access fallback */}
      {!permissionsLoading && !hasAnyAccess && (!requestableRoles || requestableRoles.length === 0) && (
        <Alert variant="default" className="mb-8 bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-950 dark:border-blue-800 dark:text-blue-200">
          <AlertCircle className="h-4 w-4 !text-blue-600 dark:!text-blue-400" />
          <AlertDescription className="ml-2">
            {t('home:noAccess.message')} {t('home:noAccess.contactAdmin', 'Please contact an administrator to request access to the application.')}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
