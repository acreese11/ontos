import { Link } from 'react-router-dom';

interface CollectionBreakdownProps {
  collections: {
    id: string;
    name: string;
    count: number;
  }[];
}

export default function CollectionBreakdown({ collections }: CollectionBreakdownProps) {
  return (
    <div className="flex flex-col gap-0.5 mt-2">
      {collections.map(({ id, name, count }) => (
        <Link
          key={id}
          to={`/concepts/browser?source=${encodeURIComponent(id)}`}
          className="flex items-center justify-between px-2 py-0.5 rounded hover:bg-accent/50 transition-colors group"
        >
          <span className="text-xs text-muted-foreground truncate">{name}</span>
          <span className="text-sm font-semibold text-foreground group-hover:underline">
            {count}
          </span>
        </Link>
      ))}
    </div>
  );
}
