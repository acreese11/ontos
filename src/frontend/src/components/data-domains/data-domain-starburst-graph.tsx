import React, { useCallback, useEffect, useMemo } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Position,
  Handle,
  ReactFlowProvider,
  useReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  BaseEdge,
  EdgeProps,
  getStraightPath,
  useStore,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { DataDomain } from '@/types/data-domain';

interface DataDomainStarburstGraphProps {
  domains: DataDomain[];
  hubLabel?: string;
  onNodeClick?: (domainId: string) => void;
}

// ── Layout constants ──────────────────────────────────────────
const peerWidth = 150;
const peerHeight = 64;
const hubWidth = 180;
const hubHeight = 72;
const ringBaseRadius = 260;
const cx = 0;
const cy = 0;

// Deterministic pseudo-random in [-1, 1] from a string seed.
function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) / 0xffffffff) * 2 - 1;
}

// ── Node components ───────────────────────────────────────────
interface PeerData {
  label: string;
  domainId: string;
  subDomainCount: number;
  onClick?: (id: string) => void;
  floatDelay: number;
  floatDistance: number;
}

const PeerNode = ({ data }: { data: PeerData }) => (
  <div
    onClick={() => data.onClick?.(data.domainId)}
    className="cursor-pointer group relative"
    style={{
      width: peerWidth,
      height: peerHeight,
      animation: `domain-float 6s ease-in-out infinite`,
      animationDelay: `${data.floatDelay}s`,
      ['--float-distance' as any]: `${data.floatDistance}px`,
    }}
  >
    <Handle type="target" position={Position.Top} id="t-t" style={{ background: 'transparent', border: 'none', opacity: 0 }} />
    <div className="w-full h-full rounded-2xl flex flex-col items-center justify-center text-center px-3 backdrop-blur-sm bg-card/80 border border-border/60 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.15)] transition-all duration-300 group-hover:scale-105 group-hover:shadow-[0_8px_30px_-6px_rgba(99,102,241,0.35)] group-hover:border-primary/60 group-hover:bg-card">
      <div className="text-sm font-medium leading-tight">{data.label}</div>
      {data.subDomainCount > 0 && (
        <div className="text-[10px] text-muted-foreground mt-0.5">
          {data.subDomainCount} sub-domain{data.subDomainCount === 1 ? '' : 's'}
        </div>
      )}
    </div>
  </div>
);

const HubNode = ({ data }: { data: { label: string } }) => (
  <div
    className="rounded-full flex items-center justify-center text-center text-sm font-semibold bg-gradient-to-br from-primary to-primary/70 text-primary-foreground shadow-[0_0_40px_-4px_rgba(99,102,241,0.6)] border border-primary-foreground/10"
    style={{
      width: hubWidth,
      height: hubHeight,
      animation: 'domain-hub-pulse 5s ease-in-out infinite',
    }}
  >
    <Handle type="source" position={Position.Top} id="s-t" style={{ background: 'transparent', border: 'none', opacity: 0 }} />
    {data.label}
  </div>
);

const nodeTypes = { peer: PeerNode, hub: HubNode };

// ── Geometry helpers ──────────────────────────────────────────
function pillIntersection(cxN: number, cyN: number, w: number, h: number, tx: number, ty: number): [number, number] {
  const dx = tx - cxN;
  const dy = ty - cyN;
  if (dx === 0 && dy === 0) return [cxN, cyN];
  const angle = Math.atan2(dy, dx);
  const W = w / 2;
  const H = h / 2;
  if (W <= H) {
    const r = Math.min(W, H);
    return [cxN + r * Math.cos(angle), cyN + r * Math.sin(angle)];
  }
  const F = W - H;
  const sinA = Math.sin(angle);
  if (Math.abs(sinA) > 1e-6) {
    const t = Math.abs(H / sinA);
    const xOff = t * Math.cos(angle);
    if (Math.abs(xOff) <= F) {
      const ySign = sinA >= 0 ? 1 : -1;
      return [cxN + xOff, cyN + ySign * H];
    }
  }
  const cosA = Math.cos(angle);
  const xc = (cosA >= 0 ? 1 : -1) * F;
  const disc = H * H - xc * xc * sinA * sinA;
  if (disc < 0) return [cxN + W * cosA, cyN + H * sinA];
  const t = cosA * xc + Math.sqrt(disc);
  return [cxN + t * cosA, cyN + t * sinA];
}

function rectIntersection(cxN: number, cyN: number, w: number, h: number, tx: number, ty: number): [number, number] {
  const dx = tx - cxN;
  const dy = ty - cyN;
  if (dx === 0 && dy === 0) return [cxN, cyN];
  const tX = dx !== 0 ? (w / 2) / Math.abs(dx) : Infinity;
  const tY = dy !== 0 ? (h / 2) / Math.abs(dy) : Infinity;
  const t = Math.min(tX, tY);
  return [cxN + t * dx, cyN + t * dy];
}

// ── Floating edge ─────────────────────────────────────────────
function FloatingEdge({ id, source, target, markerEnd, style }: EdgeProps) {
  const sourceNode = useStore(useCallback((s: any) => s.nodeInternals.get(source), [source]));
  const targetNode = useStore(useCallback((s: any) => s.nodeInternals.get(target), [target]));

  if (!sourceNode || !targetNode) return null;

  const sPos = sourceNode.positionAbsolute ?? sourceNode.position;
  const tPos = targetNode.positionAbsolute ?? targetNode.position;
  const sW = sourceNode.width ?? 0;
  const sH = sourceNode.height ?? 0;
  const tW = targetNode.width ?? 0;
  const tH = targetNode.height ?? 0;
  if (!sPos || !tPos || !sW || !sH || !tW || !tH) return null;

  const sCx = sPos.x + sW / 2;
  const sCy = sPos.y + sH / 2;
  const tCx = tPos.x + tW / 2;
  const tCy = tPos.y + tH / 2;

  const sourceIsPill = sourceNode.type === 'hub';
  const targetIsPill = targetNode.type === 'hub';
  const [sx, sy] = sourceIsPill
    ? pillIntersection(sCx, sCy, sW, sH, tCx, tCy)
    : rectIntersection(sCx, sCy, sW, sH, tCx, tCy);
  const [tx, ty] = targetIsPill
    ? pillIntersection(tCx, tCy, tW, tH, sCx, sCy)
    : rectIntersection(tCx, tCy, tW, tH, sCx, sCy);

  const [edgePath] = getStraightPath({ sourceX: sx, sourceY: sy, targetX: tx, targetY: ty });
  return (
    <BaseEdge
      id={id}
      path={edgePath}
      markerEnd={markerEnd}
      style={style}
      className="domain-edge-breathe"
    />
  );
}

const edgeTypes = { floating: FloatingEdge };

// ── Layout ────────────────────────────────────────────────────
function computeStarburst(
  domains: DataDomain[],
  hubLabel: string,
  handleNodeClick: (id: string) => void,
): { nodes: Node[]; edges: Edge[] } {
  const roots = domains
    .filter(d => !d.parent_id)
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name));

  const nodes: Node[] = [
    {
      id: '__hub__',
      type: 'hub',
      position: { x: cx - hubWidth / 2, y: cy - hubHeight / 2 },
      data: { label: hubLabel },
      draggable: false,
      selectable: false,
    },
  ];
  const edges: Edge[] = [];

  const n = roots.length;
  if (n === 0) return { nodes, edges };

  roots.forEach((d, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
    const px = cx + ringBaseRadius * Math.cos(angle) - peerWidth / 2;
    const py = cy + ringBaseRadius * Math.sin(angle) - peerHeight / 2;

    const children = domains.filter(c => c.parent_id === d.id);

    const floatDelay = (hash(d.id + ':delay') + 1) * 3; // 0..6s
    const floatDistance = 6 + Math.abs(hash(d.id + ':amp')) * 6; // 6..12px

    nodes.push({
      id: d.id,
      type: 'peer',
      position: { x: px, y: py },
      data: {
        label: d.name,
        domainId: d.id,
        subDomainCount: children.length,
        onClick: handleNodeClick,
        floatDelay,
        floatDistance,
      },
      draggable: false,
    });
    edges.push({
      id: `e-hub-${d.id}`,
      source: '__hub__',
      target: d.id,
      type: 'floating',
      animated: false,
      style: { stroke: 'hsl(var(--primary) / 0.45)', strokeWidth: 1.25 },
    });
  });

  return { nodes, edges };
}

// ── Inner component ──────────────────────────────────────────
const DataDomainStarburstInner: React.FC<DataDomainStarburstGraphProps> = ({ domains, hubLabel = 'Safe Skies', onNodeClick }) => {
  const { fitView } = useReactFlow();

  const handleNodeClick = useCallback((id: string) => {
    onNodeClick?.(id);
  }, [onNodeClick]);

  const { nodes, edges } = useMemo(
    () => computeStarburst(domains, hubLabel, handleNodeClick),
    [domains, hubLabel, handleNodeClick],
  );

  useEffect(() => {
    const t = setTimeout(() => fitView({ padding: 0.18, duration: 400 }), 60);
    return () => clearTimeout(t);
  }, [nodes, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      fitView
      fitViewOptions={{ padding: 0.18 }}
      proOptions={{ hideAttribution: true }}
      nodesConnectable={false}
      panOnDrag
      panOnScroll={false}
      zoomOnScroll
      zoomOnPinch
      zoomOnDoubleClick
      minZoom={0.3}
      maxZoom={2.5}
      defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
    >
      <Background variant={BackgroundVariant.Dots} gap={24} size={1} className="opacity-30" />
      <Controls
        showInteractive={false}
        className="!shadow-md !border !border-border/60 !bg-card/80 !backdrop-blur"
      />
    </ReactFlow>
  );
};

const graphHeight = 480;

export const DataDomainStarburstGraph: React.FC<DataDomainStarburstGraphProps> = (props) => {
  return (
    <>
      <style>{`
        @keyframes domain-float {
          0%, 100% { transform: translateY(0px); }
          50%      { transform: translateY(calc(-1 * var(--float-distance, 8px))); }
        }
        @keyframes domain-hub-pulse {
          0%, 100% { transform: scale(1);    box-shadow: 0 0 40px -4px rgba(99,102,241,0.55); }
          50%      { transform: scale(1.03); box-shadow: 0 0 60px -4px rgba(99,102,241,0.75); }
        }
        @keyframes domain-edge-breathe {
          0%, 100% { stroke-opacity: 0.8; }
          50%      { stroke-opacity: 1;   }
        }
        path.domain-edge-breathe {
          animation: domain-edge-breathe 5.5s ease-in-out infinite;
        }
      `}</style>
      <div
        style={{ height: graphHeight }}
        className="rounded-xl overflow-hidden border border-border/40 bg-gradient-to-br from-muted/30 via-background to-muted/20 w-full"
      >
        <ReactFlowProvider>
          <DataDomainStarburstInner {...props} />
        </ReactFlowProvider>
      </div>
    </>
  );
};
