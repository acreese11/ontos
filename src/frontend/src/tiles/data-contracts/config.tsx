import { FileText as FileTextIcon } from 'lucide-react';
import { FeatureAccessLevel } from '@/types/settings';
import { TileConfig } from '../types';
import { useDataContractsData } from './use-data-contracts-data';
import ContractStatusBreakdown from '@/components/home/contract-status-breakdown';

export const dataContractsTile: TileConfig = {
  id: 'data-contracts',
  icon: <FileTextIcon className="h-4 w-4" />,
  titleKey: 'home:overview.tiles.dataContracts.title',
  descriptionKey: 'home:overview.tiles.dataContracts.description',
  link: '/data-contracts',
  permission: 'data-contracts',
  requiredLevel: FeatureAccessLevel.READ_ONLY,
  useTileData: useDataContractsData,
  renderContent: (data) => (
    <ContractStatusBreakdown statusCounts={data.customData?.statusBreakdown || []} />
  ),
};
