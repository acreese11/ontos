import { Scale } from 'lucide-react';
import { FeatureAccessLevel } from '@/types/settings';
import { TileConfig } from '../types';
import { useComplianceData } from './use-compliance-data';
import ComplianceTrendMini from '@/components/home/compliance-trend-mini';

export const complianceTile: TileConfig = {
  id: 'compliance',
  icon: <Scale className="h-4 w-4" />,
  titleKey: 'home:overview.tiles.compliance.title',
  descriptionKey: 'home:overview.tiles.compliance.description',
  link: '/compliance',
  permission: 'compliance',
  requiredLevel: FeatureAccessLevel.READ_ONLY,
  useTileData: useComplianceData,
  renderContent: (data) => (
    <ComplianceTrendMini data={data.customData?.trendData} />
  ),
};
