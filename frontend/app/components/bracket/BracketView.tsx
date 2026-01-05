import { useCallback, useEffect, useState, useRef } from 'react';
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type ReactFlowInstance,
  ReactFlowProvider,
  Panel,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useBracketStore } from '~/store/bracketStore';
import { useUserStore } from '~/store/userStore';
import { useElkLayout, type MatchNode as MatchNodeType } from './hooks/useElkLayout';
import { MatchNode } from './nodes/MatchNode';
import { EmptySlotNode } from './nodes/EmptySlotNode';
import { BracketEdge } from './edges/BracketEdge';
import { BracketToolbar } from './controls/BracketToolbar';
import { MatchStatsModal } from './modals/MatchStatsModal';
import type { BracketMatch, MatchNodeData } from './types';

// Register node/edge types outside component to prevent re-renders
const nodeTypes = {
  match: MatchNode,
  emptySlot: EmptySlotNode,
};

const edgeTypes = {
  bracket: BracketEdge,
};

interface BracketViewProps {
  tournamentId: number;
}

// Layout constants
const BRACKET_SECTION_GAP = 180;
const NODE_WIDTH = 220;
const NODE_HEIGHT = 100;

/**
 * Create edges only when winner is set and winning team appears in target match
 */
function createAdvancementEdges(matches: BracketMatch[]): Edge[] {
  const matchMap = new Map(matches.map(m => [m.id, m]));

  return matches
    .filter(m => {
      // Must have a next match and a winner
      if (!m.nextMatchId || !m.winner) return false;
      return true;
    })
    .map(match => {
      const targetMatch = matchMap.get(match.nextMatchId!);
      if (!targetMatch) return null;

      // Get the winning team
      const winningTeam = match.winner === 'radiant' ? match.radiantTeam : match.direTeam;
      if (!winningTeam?.pk) return null;

      // Check if winning team is actually in the target match
      const winnerInTarget =
        targetMatch.radiantTeam?.pk === winningTeam.pk ||
        targetMatch.direTeam?.pk === winningTeam.pk;

      if (!winnerInTarget) return null;

      return {
        id: `${match.id}-${match.nextMatchId}`,
        source: match.id,
        target: match.nextMatchId!,
        type: 'bracket',
        data: { isWinnerPath: true },
      };
    })
    .filter((e): e is Edge => e !== null);
}

/**
 * Convert matches to ReactFlow nodes
 */
function matchesToNodes(matches: BracketMatch[]): MatchNodeType[] {
  return matches.map((match) => ({
    id: match.id,
    type: 'match' as const,
    position: { x: 0, y: 0 },
    data: { ...match } as MatchNodeData,
  }));
}

/**
 * Create structural edges for ELK layout calculation
 */
function createStructuralEdges(matches: BracketMatch[]): Edge[] {
  return matches
    .filter(m => m.nextMatchId)
    .map(match => ({
      id: `struct-${match.id}-${match.nextMatchId}`,
      source: match.id,
      target: match.nextMatchId!,
      type: 'bracket',
      hidden: true,
    }));
}

function BracketFlowInner({ tournamentId }: BracketViewProps) {
  const isStaff = useUserStore((state) => state.isStaff());
  const tournament = useUserStore((state) => state.tournament);

  const {
    matches,
    isDirty,
    isVirtual,
    isLoading,
    loadBracket,
    startPolling,
    stopPolling,
  } = useBracketStore();

  const { getLayoutedElements } = useElkLayout();
  const { setViewport, getViewport } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState<MatchNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [dividerY, setDividerY] = useState<number>(0);
  const layoutCompleteRef = useRef(false);

  // Selected match for stats modal
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const selectedMatch = matches.find((m) => m.id === selectedMatchId) ?? null;

  // Load bracket on mount
  useEffect(() => {
    loadBracket(tournamentId);
    return () => stopPolling();
  }, [tournamentId, loadBracket, stopPolling]);

  // Start polling for live updates (when not editing)
  useEffect(() => {
    if (!isDirty) {
      startPolling(tournamentId, 5000);
    } else {
      stopPolling();
    }
    return () => stopPolling();
  }, [isDirty, tournamentId, startPolling, stopPolling]);

  // Layout matches using ELK when matches change
  useEffect(() => {
    if (matches.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const layoutBracket = async () => {
      // Separate matches by bracket type
      const winnersMatches = matches.filter(m => m.bracketType === 'winners');
      const losersMatches = matches.filter(m => m.bracketType === 'losers');
      const grandFinalsMatches = matches.filter(m => m.bracketType === 'grand_finals');

      // Create nodes
      const winnersNodes = matchesToNodes(winnersMatches);
      const losersNodes = matchesToNodes(losersMatches);

      // Create structural edges for layout
      const winnersEdges = createStructuralEdges(winnersMatches);
      const losersEdges = createStructuralEdges(losersMatches);

      // Layout winners bracket
      const winners = await getLayoutedElements(winnersNodes, winnersEdges, {
        nodeWidth: NODE_WIDTH,
        nodeHeight: NODE_HEIGHT,
      });

      // Layout losers bracket
      const losers = await getLayoutedElements(losersNodes, losersEdges, {
        nodeWidth: NODE_WIDTH,
        nodeHeight: NODE_HEIGHT,
      });

      // Calculate offset for losers bracket
      const winnersMaxY = Math.max(...winners.nodes.map(n => n.position.y + NODE_HEIGHT), 0);
      const losersOffset = winnersMaxY + BRACKET_SECTION_GAP;

      // Set divider position
      setDividerY(winnersMaxY + BRACKET_SECTION_GAP / 2);

      // Apply offset to losers nodes
      const offsetLosers: MatchNodeType[] = losers.nodes.map(node => ({
        ...node,
        position: { x: node.position.x, y: node.position.y + losersOffset },
      }));

      // Position grand finals
      const winnersMaxX = Math.max(...winners.nodes.map(n => n.position.x), 0);
      const losersMaxX = Math.max(...offsetLosers.map(n => n.position.x), 0);
      const grandFinalsX = Math.max(winnersMaxX, losersMaxX) + 300;
      const grandFinalsY = losersOffset / 2;

      const grandFinalsNodes: MatchNodeType[] = grandFinalsMatches.map((match, i) => ({
        id: match.id,
        type: 'match' as const,
        position: { x: grandFinalsX, y: grandFinalsY + i * (NODE_HEIGHT + 30) },
        data: { ...match } as MatchNodeData,
      }));

      // Combine all nodes
      const allNodes = [...winners.nodes, ...offsetLosers, ...grandFinalsNodes];

      // Create visible edges (only for completed matches with winners)
      const visibleEdges = createAdvancementEdges(matches);

      setNodes(allNodes);
      setEdges(visibleEdges);
      layoutCompleteRef.current = true;
    };

    layoutBracket();
  }, [matches, getLayoutedElements, setNodes, setEdges]);

  // Left-align viewport after layout is complete
  useEffect(() => {
    if (nodes.length > 0 && layoutCompleteRef.current) {
      // Small delay to ensure ReactFlow has rendered
      const timer = setTimeout(() => {
        // Calculate bounds of all nodes
        const minX = Math.min(...nodes.map(n => n.position.x));
        const minY = Math.min(...nodes.map(n => n.position.y));
        const maxY = Math.max(...nodes.map(n => n.position.y + NODE_HEIGHT));

        // Calculate container height (700px) and content height
        const containerHeight = 700;
        const contentHeight = maxY - minY + NODE_HEIGHT;

        // Choose zoom level - fit vertically if needed, max 1.0
        const verticalZoom = containerHeight / (contentHeight + 100);
        const zoom = Math.min(0.9, Math.max(0.4, verticalZoom));

        // Position: left-aligned with small padding, vertically centered
        const xOffset = 40; // Left padding
        const yOffset = (containerHeight - contentHeight * zoom) / 2;

        setViewport({
          x: xOffset - minX * zoom,
          y: yOffset - minY * zoom,
          zoom,
        });
      }, 50);

      return () => clearTimeout(timer);
    }
  }, [nodes, setViewport]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedMatchId(node.id);
  }, []);

  if (isLoading && matches.length === 0) {
    return (
      <div className="flex items-center justify-center h-96">
        Loading bracket...
      </div>
    );
  }

  const teams = tournament?.teams ?? [];

  return (
    <div className="w-full space-y-4">
      {/* Staff toolbar */}
      {isStaff && (
        <BracketToolbar
          tournamentId={tournamentId}
          teams={teams}
          hasMatches={matches.length > 0}
          isDirty={isDirty}
          isVirtual={isVirtual}
        />
      )}

      {/* Dirty indicator */}
      {isDirty && (
        <div className="bg-yellow-500/10 text-yellow-500 text-sm px-3 py-1 rounded">
          Unsaved changes
        </div>
      )}

      {/* Empty state */}
      {matches.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-96 text-muted-foreground">
          <p className="mb-4">No bracket generated yet.</p>
          {isStaff && teams.length >= 2 && (
            <p className="text-sm">
              Use the toolbar above to generate a bracket.
            </p>
          )}
          {teams.length < 2 && (
            <p className="text-sm">Need at least 2 teams to create a bracket.</p>
          )}
        </div>
      )}

      {/* Single ReactFlow instance for entire bracket */}
      {matches.length > 0 && (
        <div className="h-[700px] border rounded-lg overflow-hidden bg-background">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            nodesDraggable={isStaff}
            nodesConnectable={false}
            elementsSelectable={true}
            panOnDrag={true}
            zoomOnScroll={true}
            minZoom={0.3}
            maxZoom={1.5}
            defaultViewport={{ x: 40, y: 50, zoom: 0.8 }}
          >
            <Background gap={20} size={1} />

            {/* Bracket section label - Winners */}
            <Panel position="top-left" className="bg-background/80 px-3 py-1 rounded text-sm font-medium text-foreground">
              Winners Bracket
            </Panel>
          </ReactFlow>
        </div>
      )}

      {/* Match stats modal */}
      <MatchStatsModal
        match={selectedMatch}
        isOpen={!!selectedMatchId}
        onClose={() => setSelectedMatchId(null)}
      />
    </div>
  );
}

export function BracketView({ tournamentId }: BracketViewProps) {
  return (
    <ReactFlowProvider>
      <BracketFlowInner tournamentId={tournamentId} />
    </ReactFlowProvider>
  );
}
