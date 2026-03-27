import { useTranslation } from 'react-i18next';
import OverviewTile from './overview-tile';
import type { TileConfig } from '@/tiles';

interface ConnectedOverviewTileProps {
  tile: TileConfig;
}

/**
 * Wrapper component that connects a tile configuration to the OverviewTile component.
 * Handles calling the tile's data hook and passing the data to OverviewTile.
 *
 * This component exists to properly handle React's Rules of Hooks - we can't call
 * hooks conditionally in a map function, so each tile needs its own component.
 */
export default function ConnectedOverviewTile({ tile }: ConnectedOverviewTileProps) {
  const { t } = useTranslation();
  const data = tile.useTileData();

  return (
    <OverviewTile
      icon={tile.icon}
      title={t(tile.titleKey)}
      value={data.value}
      loading={data.loading}
      error={data.error}
      link={tile.link}
      description={t(tile.descriptionKey)}
    >
      {tile.renderContent?.(data)}
    </OverviewTile>
  );
}
