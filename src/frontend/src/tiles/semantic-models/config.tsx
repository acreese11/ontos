import { Network } from 'lucide-react';
import { FeatureAccessLevel } from '@/types/settings';
import { TileConfig } from '../types';
import { useSemanticModelsData } from './use-semantic-models-data';
import CollectionBreakdown from '@/components/home/collection-breakdown';

export const semanticModelsTile: TileConfig = {
  id: 'semantic-models',
  icon: <Network className="h-4 w-4" />,
  titleKey: 'home:overview.tiles.semanticModels.title',
  descriptionKey: 'home:overview.tiles.semanticModels.description',
  link: '/semantic-models',
  permission: 'semantic-models',
  requiredLevel: FeatureAccessLevel.READ_ONLY,
  useTileData: useSemanticModelsData,
  renderContent: (data) => (
    <CollectionBreakdown collections={data.customData?.collectionBreakdown || []} />
  ),
};
