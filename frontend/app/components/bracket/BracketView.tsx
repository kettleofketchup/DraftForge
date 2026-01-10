import { useCallback, useEffect, useState, useRef, useMemo } from 'react';
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
import './bracket-styles.css';

import { useBracketStore } from '~/store/bracketStore';
import { useUserStore } from '~/store/userStore';
import { useElkLayout, type MatchNode as MatchNodeType } from './hooks/useElkLayout';
import { MatchNode } from './nodes/MatchNode';
import { EmptySlotNode } from './nodes/EmptySlotNode';
import { DividerNode, type DividerNodeData } from './nodes/DividerNode';
import { BracketEdge } from './edges/BracketEdge';
import { BracketToolbar } from './controls/BracketToolbar';
import { MatchStatsModal } from './modals/MatchStatsModal';
import type { BracketMatch, MatchNodeData, BadgeMapping } from './types';
import { buildBadgeMapping } from './utils/badgeUtils';

// Register node/edge types outside component to prevent re-renders
const nodeTypes = {
  match: MatchNode,
  emptySlot: EmptySlotNode,
  divider: DividerNode,
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
const NODE_HEIGHT = 120; // Increased for better spacing
const NODE_VERTICAL_GAP = 30; // Minimum gap between nodes
const ROUND_HORIZONTAL_GAP = 180; // Gap between rounds

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
function matchesToNodes(matches: BracketMatch[], badgeMapping: BadgeMapping): MatchNodeType[] {
  return matches.map((match) => ({
    id: match.id,
    type: 'match' as const,
    position: { x: 0, y: 0 },
    data: { ...match, badgeMapping } as MatchNodeData,
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

  // Pre-compute badge mapping for all matches
  const badgeMapping = useMemo(() => buildBadgeMapping(matches), [matches]);

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
      const winnersNodes = matchesToNodes(winnersMatches, badgeMapping);
      const losersNodes = matchesToNodes(losersMatches, badgeMapping);

      // Create structural edges for layout
      const winnersEdges = createStructuralEdges(winnersMatches);
      const losersEdges = createStructuralEdges(losersMatches);

      /**
       * Custom bracket layout with collision detection
       * Places nodes by round, vertically centered to their targets
       */
      const layoutBracketNodes = (
        nodes: MatchNodeType[],
        matchList: BracketMatch[]
      ): MatchNodeType[] => {
        if (nodes.length === 0) return nodes;

        // Create lookup maps
        const nodeById = new Map(nodes.map(n => [n.id, n]));
        const matchById = new Map(matchList.map(m => [m.id, m]));

        // Group nodes by round
        const roundGroups = new Map<number, MatchNodeType[]>();
        nodes.forEach(node => {
          const round = (node.data as MatchNodeData).round;
          if (!roundGroups.has(round)) roundGroups.set(round, []);
          roundGroups.get(round)!.push(node);
        });

        // Sort rounds
        const rounds = Array.from(roundGroups.keys()).sort((a, b) => a - b);

        // Position round 1 nodes first (they have no source)
        const round1Nodes = roundGroups.get(rounds[0]) || [];
        round1Nodes.sort((a, b) => (a.data as MatchNodeData).position - (b.data as MatchNodeData).position);

        round1Nodes.forEach((node, i) => {
          node.position.x = 0;
          node.position.y = i * (NODE_HEIGHT + NODE_VERTICAL_GAP);
        });

        // Position subsequent rounds - center between source nodes
        for (let i = 1; i < rounds.length; i++) {
          const round = rounds[i];
          const roundNodes = roundGroups.get(round) || [];
          const xPos = i * (NODE_WIDTH + ROUND_HORIZONTAL_GAP);

          roundNodes.sort((a, b) => (a.data as MatchNodeData).position - (b.data as MatchNodeData).position);

          roundNodes.forEach(node => {
            node.position.x = xPos;

            // Find source nodes that feed into this node
            const sourceNodes: MatchNodeType[] = [];
            matchList.forEach(match => {
              if (match.nextMatchId === node.id) {
                const sourceNode = nodeById.get(match.id);
                if (sourceNode) sourceNodes.push(sourceNode);
              }
            });

            if (sourceNodes.length > 0) {
              // Center between source nodes
              const sourceYs = sourceNodes.map(n => n.position.y + NODE_HEIGHT / 2);
              const avgY = sourceYs.reduce((a, b) => a + b, 0) / sourceYs.length;
              node.position.y = avgY - NODE_HEIGHT / 2;
            }
          });
        }

        // Collision detection - resolve overlaps
        const resolveCollisions = (nodes: MatchNodeType[], maxIterations = 10) => {
          for (let iter = 0; iter < maxIterations; iter++) {
            let hasCollision = false;

            // Group by round for collision detection within same column
            const byRound = new Map<number, MatchNodeType[]>();
            nodes.forEach(n => {
              const round = (n.data as MatchNodeData).round;
              if (!byRound.has(round)) byRound.set(round, []);
              byRound.get(round)!.push(n);
            });

            byRound.forEach(roundNodes => {
              // Sort by Y position
              roundNodes.sort((a, b) => a.position.y - b.position.y);

              for (let i = 0; i < roundNodes.length - 1; i++) {
                const nodeA = roundNodes[i];
                const nodeB = roundNodes[i + 1];

                const gap = nodeB.position.y - (nodeA.position.y + NODE_HEIGHT);
                if (gap < NODE_VERTICAL_GAP) {
                  // Collision detected - push apart
                  const overlap = NODE_VERTICAL_GAP - gap;
                  nodeA.position.y -= overlap / 2;
                  nodeB.position.y += overlap / 2;
                  hasCollision = true;
                }
              }
            });

            if (!hasCollision) break;
          }
        };

        resolveCollisions(nodes);
        return nodes;
      };

      // Layout winners bracket with custom algorithm
      const layoutedWinners = layoutBracketNodes(winnersNodes, winnersMatches);

      // Layout losers bracket with custom algorithm
      const layoutedLosers = layoutBracketNodes(losersNodes, losersMatches);

      // Calculate offset for losers bracket
      const winnersMaxY = Math.max(...layoutedWinners.map(n => n.position.y + NODE_HEIGHT), 0);
      const losersOffset = winnersMaxY + BRACKET_SECTION_GAP;

      // Set divider position
      setDividerY(winnersMaxY + BRACKET_SECTION_GAP / 2);

      // Apply offset to losers nodes
      const offsetLosers: MatchNodeType[] = layoutedLosers.map(node => ({
        ...node,
        position: { x: node.position.x, y: node.position.y + losersOffset },
      }));

      // Position grand finals - in the winners section, aligned with winners final
      const winnersMaxX = Math.max(...layoutedWinners.map(n => n.position.x), 0);
      const losersMaxX = Math.max(...offsetLosers.map(n => n.position.x), 0);
      const grandFinalsX = Math.max(winnersMaxX, losersMaxX) + ROUND_HORIZONTAL_GAP * 1.5; // Extra space for grand finals

      // Find the winners final for vertical alignment
      const winnersFinal = layoutedWinners.find(n => {
        const match = winnersMatches.find(m => m.id === n.id);
        return match && match.nextMatchId?.startsWith('gf-');
      });

      // Position grand finals aligned with winners final (in winners section, above divider)
      let grandFinalsY = winnersFinal ? winnersFinal.position.y : 0;

      const grandFinalsNodes: MatchNodeType[] = grandFinalsMatches.map((match, i) => ({
        id: match.id,
        type: 'match' as const,
        position: { x: grandFinalsX, y: grandFinalsY + i * (NODE_HEIGHT + 30) },
        data: { ...match, badgeMapping } as MatchNodeData,
      }));

      // Calculate bracket bounds for divider - extend far beyond visible area
      const allMatchNodes = [...layoutedWinners, ...offsetLosers, ...grandFinalsNodes];
      const minX = Math.min(...allMatchNodes.map(n => n.position.x), 0);
      const maxX = Math.max(...allMatchNodes.map(n => n.position.x + NODE_WIDTH), 0);
      const dividerWidth = 5000; // Very wide to span entire viewport

      // Create divider node between winners and losers (behind other nodes)
      const dividerNode: Node<DividerNodeData> = {
        id: 'divider-winners-losers',
        type: 'divider',
        position: { x: -2000, y: winnersMaxY + BRACKET_SECTION_GAP / 2 - 10 },
        data: { width: dividerWidth, label: 'Losers Bracket' },
        selectable: false,
        draggable: false,
        className: 'divider-node',
      };

      // Combine all nodes - divider first so it renders behind
      const allNodes = [
        dividerNode,
        ...layoutedWinners,
        ...offsetLosers,
        ...grandFinalsNodes,
      ];

      // Create visible edges (only for completed matches with winners)
      const visibleEdges = createAdvancementEdges(matches);

      setNodes(allNodes as MatchNodeType[]);
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
        // Calculate bounds of match nodes only (exclude divider)
        const matchNodes = nodes.filter(n => n.type === 'match');
        if (matchNodes.length === 0) return;

        const minX = Math.min(...matchNodes.map(n => n.position.x));
        const minY = Math.min(...matchNodes.map(n => n.position.y));
        const maxY = Math.max(...matchNodes.map(n => n.position.y + NODE_HEIGHT));

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
        <div className="h-[700px] border rounded-lg overflow-hidden bg-background" data-testid="bracketContainer">
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
