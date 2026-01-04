import { useCallback, useEffect, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type OnNodesChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useBracketStore } from '~/store/bracketStore';
import { useUserStore } from '~/store/userStore';
import { useElkLayout, layoutDoubleElimination } from './hooks/useElkLayout';
import { MatchNode } from './nodes/MatchNode';
import { EmptySlotNode } from './nodes/EmptySlotNode';
import { BracketEdge } from './edges/BracketEdge';
import { BracketToolbar } from './controls/BracketToolbar';
import { MatchStatsModal } from './modals/MatchStatsModal';

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

export function BracketView({ tournamentId }: BracketViewProps) {
  const isStaff = useUserStore((state) => state.isStaff());
  const tournament = useUserStore((state) => state.tournament);

  const {
    matches,
    isDirty,
    isVirtual,
    isLoading,
    setNodes: setStoreNodes,
    setEdges: setStoreEdges,
    loadBracket,
    startPolling,
    stopPolling,
  } = useBracketStore();

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const { getLayoutedElements } = useElkLayout();

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

  // Re-layout when matches change
  useEffect(() => {
    async function layout() {
      if (matches.length === 0) return;

      try {
        const { nodes: layoutedNodes, edges: layoutedEdges } =
          await layoutDoubleElimination(matches, getLayoutedElements);

        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
        setStoreNodes(layoutedNodes);
        setStoreEdges(layoutedEdges);
      } catch (error) {
        console.error('Failed to layout bracket:', error);
      }
    }
    layout();
  }, [matches, getLayoutedElements, setNodes, setEdges, setStoreNodes, setStoreEdges]);

  // Handle node drag (staff only)
  const handleNodesChange: OnNodesChange = useCallback(
    (changes) => {
      if (!isStaff) {
        // Filter out position changes for non-staff
        changes = changes.filter((c) => c.type !== 'position');
      }
      onNodesChange(changes);
    },
    [isStaff, onNodesChange]
  );

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
    <div className="h-[600px] w-full">
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
        <div className="bg-yellow-500/10 text-yellow-500 text-sm px-3 py-1 rounded mb-2">
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

      {/* React Flow canvas */}
      {matches.length > 0 && (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={handleNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={isStaff}
          nodesConnectable={false}
          elementsSelectable={true}
        >
          <Background />
          <Controls />
        </ReactFlow>
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
