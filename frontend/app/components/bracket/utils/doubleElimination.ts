import type { BracketMatch, BracketSectionType } from '../types';
import type { TeamType } from '~/components/tournament/types';

/**
 * Double elimination bracket generator.
 *
 * TODO: Algorithm may need refinement for non-power-of-2 team counts.
 * The losers bracket structure should be validated with real tournament data.
 *
 * For N teams:
 * - Winners Bracket: ceil(log2(N)) rounds
 * - Losers Bracket: 2 * (ceil(log2(N)) - 1) rounds
 * - Grand Finals: 1-2 matches
 */
export function generateDoubleElimination(teams: TeamType[]): BracketMatch[] {
  const n = teams.length;
  if (n < 2) {
    throw new Error('Need at least 2 teams for a bracket');
  }

  const matches: BracketMatch[] = [];
  const winnersRounds = Math.ceil(Math.log2(n));

  // Pad to power of 2 for clean bracket
  const bracketSize = Math.pow(2, winnersRounds);

  let matchId = 1;

  // Generate Winners Bracket
  const winnersMatches = generateWinnersBracket(bracketSize, winnersRounds, matchId);
  matchId += winnersMatches.length;
  matches.push(...winnersMatches);

  // Generate Losers Bracket
  const losersRounds = 2 * (winnersRounds - 1);
  const losersMatches = generateLosersBracket(bracketSize, losersRounds, matchId);
  matchId += losersMatches.length;
  matches.push(...losersMatches);

  // Wire loser paths from winners bracket to losers bracket
  wireLoserPaths(winnersMatches, losersMatches);

  // Generate Grand Finals
  const { grandFinals, connections } = generateGrandFinals(matchId, winnersMatches, losersMatches);
  matches.push(...grandFinals);

  // Apply connections from finalists to grand finals
  if (connections.winnersFinalistId) {
    const winnersFinalist = matches.find((m) => m.id === connections.winnersFinalistId);
    if (winnersFinalist) {
      winnersFinalist.nextMatchId = connections.grandFinalsId;
      winnersFinalist.nextMatchSlot = 'radiant';
    }
  }
  if (connections.losersFinalistId) {
    const losersFinalist = matches.find((m) => m.id === connections.losersFinalistId);
    if (losersFinalist) {
      losersFinalist.nextMatchId = connections.grandFinalsId;
      losersFinalist.nextMatchSlot = 'dire';
    }
  }

  return matches;
}

function generateWinnersBracket(
  bracketSize: number,
  rounds: number,
  startId: number
): BracketMatch[] {
  const matches: BracketMatch[] = [];
  let matchId = startId;

  for (let round = 1; round <= rounds; round++) {
    const matchesInRound = bracketSize / Math.pow(2, round);

    for (let position = 0; position < matchesInRound; position++) {
      const match: BracketMatch = {
        id: `w-${matchId}`,
        round,
        position,
        bracketType: 'winners',
        eliminationType: 'double',
        status: 'pending',
      };

      // Set next match (winner advances)
      if (round < rounds) {
        const nextPosition = Math.floor(position / 2);
        const nextMatchId = matchId + matchesInRound - position + nextPosition;
        match.nextMatchId = `w-${nextMatchId}`;
        match.nextMatchSlot = position % 2 === 0 ? 'radiant' : 'dire';
      }

      matches.push(match);
      matchId++;
    }
  }

  return matches;
}

function generateLosersBracket(
  bracketSize: number,
  rounds: number,
  startId: number
): BracketMatch[] {
  const matches: BracketMatch[] = [];
  let matchId = startId;

  // Losers bracket has alternating "drop-down" and "elimination" rounds
  for (let round = 1; round <= rounds; round++) {
    // Calculate matches in this round
    const winnersRound = Math.ceil(round / 2);
    const matchesInRound = bracketSize / Math.pow(2, winnersRound + 1);

    for (let position = 0; position < matchesInRound; position++) {
      const match: BracketMatch = {
        id: `l-${matchId}`,
        round,
        position,
        bracketType: 'losers',
        eliminationType: 'double',
        status: 'pending',
      };

      // Set next match
      if (round < rounds) {
        const nextMatchId = matchId + matchesInRound;
        match.nextMatchId = `l-${nextMatchId}`;
        match.nextMatchSlot = position % 2 === 0 ? 'radiant' : 'dire';
      }

      matches.push(match);
      matchId++;
    }
  }

  return matches;
}

/**
 * Wire loser paths from winners bracket to losers bracket.
 *
 * Pattern:
 * - WB R1 losers → LB R1 (major round): 2 WB matches feed 1 LB match
 * - WB R2+ losers → LB even rounds (minor rounds): 1:1 mapping, dire slot
 *
 * For 8 teams:
 * - WB R1 (4 matches) → LB R1 (2 matches): positions 0,1→match 0; 2,3→match 1
 * - WB R2 (2 matches) → LB R2 (2 matches): 1:1 into dire slots
 * - WB Finals (1 match) → LB Finals (1 match): into dire slot
 */
function wireLoserPaths(
  winnersMatches: BracketMatch[],
  losersMatches: BracketMatch[]
): void {
  const winnersRounds = Math.max(...winnersMatches.map((m) => m.round));

  for (const wMatch of winnersMatches) {
    // Determine which LB round this WB round feeds into
    // WB R1 → LB R1, WB R2 → LB R2, WB R3 → LB R4, WB R4 → LB R6, etc.
    const lbRound = wMatch.round === 1 ? 1 : 2 * (wMatch.round - 1);

    // Find LB matches in the target round
    const lbMatchesInRound = losersMatches.filter((m) => m.round === lbRound);

    if (wMatch.round === 1) {
      // Major round (LB R1): 2 WB matches → 1 LB match
      // Even WB position → radiant, odd → dire
      const lbPosition = Math.floor(wMatch.position / 2);
      const lbMatch = lbMatchesInRound.find((m) => m.position === lbPosition);
      if (lbMatch) {
        wMatch.loserNextMatchId = lbMatch.id;
        wMatch.loserNextMatchSlot = wMatch.position % 2 === 0 ? 'radiant' : 'dire';
      }
    } else if (wMatch.round < winnersRounds) {
      // Minor rounds (LB R2, R4, etc.): 1:1 mapping, dire slot
      const lbMatch = lbMatchesInRound.find((m) => m.position === wMatch.position);
      if (lbMatch) {
        wMatch.loserNextMatchId = lbMatch.id;
        wMatch.loserNextMatchSlot = 'dire';
      }
    } else {
      // Winners Finals → Losers Finals (last LB round)
      const losersFinalsRound = Math.max(...losersMatches.map((m) => m.round));
      const losersFinals = losersMatches.find(
        (m) => m.round === losersFinalsRound && m.position === 0
      );
      if (losersFinals) {
        wMatch.loserNextMatchId = losersFinals.id;
        wMatch.loserNextMatchSlot = 'dire';
      }
    }
  }
}

interface GrandFinalsResult {
  grandFinals: BracketMatch[];
  connections: {
    winnersFinalistId: string | null;
    losersFinalistId: string | null;
    grandFinalsId: string;
  };
}

function generateGrandFinals(
  startId: number,
  winnersMatches: BracketMatch[],
  losersMatches: BracketMatch[]
): GrandFinalsResult {
  const winnersFinalist = winnersMatches[winnersMatches.length - 1];
  const losersFinalist = losersMatches[losersMatches.length - 1];

  const grandFinals: BracketMatch = {
    id: `gf-${startId}`,
    round: 1,
    position: 0,
    bracketType: 'grand_finals',
    eliminationType: 'double',
    status: 'pending',
  };

  return {
    grandFinals: [grandFinals],
    connections: {
      winnersFinalistId: winnersFinalist?.id ?? null,
      losersFinalistId: losersFinalist?.id ?? null,
      grandFinalsId: grandFinals.id,
    },
  };
}

/**
 * Get round label for display
 */
export function getRoundLabel(bracketType: BracketSectionType, round: number, totalRounds?: number): string {
  switch (bracketType) {
    case 'winners':
      if (totalRounds && round === totalRounds) return 'Winners Finals';
      if (totalRounds && round === totalRounds - 1) return 'Winners Semis';
      return `Winners R${round}`;
    case 'losers':
      if (totalRounds && round === totalRounds) return 'Losers Finals';
      return `Losers R${round}`;
    case 'grand_finals':
      return 'Grand Finals';
    default:
      return `Round ${round}`;
  }
}
