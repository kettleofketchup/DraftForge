import ELK from 'elkjs/lib/elk.bundled.js';
import { useCallback } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type { BracketMatch, MatchNodeData } from '../types';

const elk = new ELK();

// ELK layout options for tournament bracket (left-to-right tree)
const defaultElkOptions = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.spacing.nodeNode': '50',
  'elk.layered.spacing.nodeNodeBetweenLayers': '150',
  'elk.portConstraints': 'FIXED_ORDER',
  'elk.layered.nodePlacement.strategy': 'SIMPLE',
};

export interface LayoutConfig {
  nodeWidth?: number;
  nodeHeight?: number;
  options?: Record<string, string>;
}

// Type for match nodes used in bracket layout
export type MatchNodeType = Node<MatchNodeData, 'match'>;

export function useElkLayout() {
  const getLayoutedElements = useCallback(
    async <T extends Node>(
      nodes: T[],
      edges: Edge[],
      config: LayoutConfig = {}
    ): Promise<{ nodes: T[]; edges: Edge[] }> => {
      const { nodeWidth = 208, nodeHeight = 100, options = {} } = config;

      const graph = {
        id: 'root',
        layoutOptions: { ...defaultElkOptions, ...options },
        children: nodes.map((node) => ({
          id: node.id,
          width: nodeWidth,
          height: nodeHeight,
          ports: [
            { id: `${node.id}-target`, properties: { side: 'WEST' } },
            { id: `${node.id}-source`, properties: { side: 'EAST' } },
          ],
        })),
        edges: edges.map((edge) => ({
          id: edge.id,
          sources: [`${edge.source}-source`],
          targets: [`${edge.target}-target`],
        })),
      };

      try {
        const layoutedGraph = await elk.layout(graph);

        const layoutedNodes = nodes.map((node) => {
          const elkNode = layoutedGraph.children?.find((n) => n.id === node.id);
          return {
            ...node,
            position: { x: elkNode?.x ?? 0, y: elkNode?.y ?? 0 },
          };
        });

        return { nodes: layoutedNodes, edges };
      } catch (error) {
        console.error('ELK layout failed:', error);
        // Return original nodes with default positions
        return {
          nodes: nodes.map((node, i) => ({
            ...node,
            position: { x: i * 250, y: i * 120 },
          })),
          edges,
        };
      }
    },
    []
  );

  return { getLayoutedElements };
}

/**
 * Layout double elimination bracket with separate sections
 */
export async function layoutDoubleElimination(
  matches: BracketMatch[],
  getLayoutedElements: ReturnType<typeof useElkLayout>['getLayoutedElements']
): Promise<{ nodes: MatchNodeType[]; edges: Edge[] }> {
  const BRACKET_GAP = 150;

  // Separate matches by bracket type
  const winnersMatches = matches.filter((m) => m.bracketType === 'winners');
  const losersMatches = matches.filter((m) => m.bracketType === 'losers');
  const grandFinalsMatches = matches.filter((m) => m.bracketType === 'grand_finals');

  // Convert to nodes - spread match into MatchNodeData to satisfy index signature
  const toNodes = (matchList: BracketMatch[]): MatchNodeType[] =>
    matchList.map((match) => ({
      id: match.id,
      type: 'match' as const,
      position: { x: 0, y: 0 },
      data: { ...match } as MatchNodeData,
    }));

  // Create edges from nextMatchId
  const toEdges = (matchList: BracketMatch[]): Edge[] =>
    matchList
      .filter((m) => m.nextMatchId)
      .map((match) => ({
        id: `${match.id}-${match.nextMatchId}`,
        source: match.id,
        target: match.nextMatchId!,
        type: 'bracket',
      }));

  // Layout winners bracket
  const winnersNodes = toNodes(winnersMatches);
  const winnersEdges = toEdges(winnersMatches);
  const winners = await getLayoutedElements(winnersNodes, winnersEdges);

  // Layout losers bracket
  const losersNodes = toNodes(losersMatches);
  const losersEdges = toEdges(losersMatches);
  const losers = await getLayoutedElements(losersNodes, losersEdges);

  // Calculate offset for losers bracket
  const winnersMaxY = Math.max(...winners.nodes.map((n) => n.position.y), 0);
  const losersOffset = winnersMaxY + BRACKET_GAP;

  // Apply offset to losers nodes
  const offsetLosers: MatchNodeType[] = losers.nodes.map((node) => ({
    ...node,
    position: { x: node.position.x, y: node.position.y + losersOffset },
  }));

  // Position grand finals
  const winnersMaxX = Math.max(...winners.nodes.map((n) => n.position.x), 0);
  const losersMaxX = Math.max(...offsetLosers.map((n) => n.position.x), 0);
  const grandFinalsX = Math.max(winnersMaxX, losersMaxX) + 250;
  const grandFinalsY = (winnersMaxY + losersOffset) / 2;

  const grandFinalsNodes: MatchNodeType[] = grandFinalsMatches.map((match) => ({
    id: match.id,
    type: 'match' as const,
    position: { x: grandFinalsX, y: grandFinalsY },
    data: { ...match } as MatchNodeData,
  }));

  // Combine all edges including cross-bracket connections
  const allEdges: Edge[] = [
    ...winners.edges,
    ...losers.edges,
    ...toEdges(grandFinalsMatches),
    // Winners final to grand finals
    ...winnersMatches
      .filter((m) => m.nextMatchId?.startsWith('gf-'))
      .map((m) => ({
        id: `${m.id}-${m.nextMatchId}`,
        source: m.id,
        target: m.nextMatchId!,
        type: 'bracket',
      })),
    // Losers final to grand finals
    ...losersMatches
      .filter((m) => m.nextMatchId?.startsWith('gf-'))
      .map((m) => ({
        id: `${m.id}-${m.nextMatchId}`,
        source: m.id,
        target: m.nextMatchId!,
        type: 'bracket',
      })),
  ];

  return {
    nodes: [...winners.nodes, ...offsetLosers, ...grandFinalsNodes],
    edges: allEdges,
  };
}
