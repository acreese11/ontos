import { ReactNode } from 'react';
import { FeatureAccessLevel } from '@/types/settings';

/**
 * Data returned by tile data fetcher hooks
 */
export interface TileData {
  value: string | number;
  loading: boolean;
  error: string | null;
  customData?: any; // For charts, breakdowns, etc.
}

/**
 * Configuration for a single overview tile
 */
export interface TileConfig {
  id: string;
  icon: ReactNode;
  titleKey: string;          // i18n key: 'home:overview.tiles.{id}.title'
  descriptionKey: string;    // i18n key: 'home:overview.tiles.{id}.description'
  link: string;
  permission: string;
  requiredLevel: FeatureAccessLevel;
  useTileData: () => TileData;
  renderContent?: (data: TileData) => ReactNode; // Optional custom content
}

/**
 * Registry of all available tiles
 */
export interface TileRegistry {
  [key: string]: TileConfig;
}
