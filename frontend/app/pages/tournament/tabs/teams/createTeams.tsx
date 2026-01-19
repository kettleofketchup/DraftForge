import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';
import { getLogger } from '~/lib/logger';

const log = getLogger('createTeams');

interface Props {
  users: UserType[];
  teamSize?: number;
}

interface TeamsViewProps {
  teams: TeamType[];
}

interface TeamViewProps {
  users: UserType[][];
}

export function createTeams(users: UserType[], teamSize: number): TeamType[] {
  // Shuffle users to add randomness to team assignment
  const shuffled = [...users];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  // Only use users that fit exactly into teams of teamSize
  const usableCount = Math.floor(shuffled.length / teamSize) * teamSize;
  const trimmed = shuffled.slice(0, usableCount);
  // Sort by MMR after shuffling for balanced assignment
  const sorted = trimmed.sort((a, b) => (b.mmr ?? 0) - (a.mmr ?? 0));
  const numTeams = Math.floor(usableCount / teamSize);
  var teams: TeamType[] = Array.from({ length: numTeams }, (_, t) => ({
    members: [],
    captain: undefined,
    name: `Team ${t + 1}`,
  }));

  // Initial greedy assignment (lowest total MMR)
  for (let i = sorted.length - 1; i >= 0; i--) {
    const user = sorted[i];
    let minSum = Infinity;
    let minTeamIdx = 0;
    for (let t = 0; t < numTeams; t++) {
      const team = teams[t];
      if ((team.members?.length ?? 0) >= teamSize) continue;
      const sum = (team.members ?? []).reduce((a: number, u: UserType) => a + (u.mmr ?? 0), 0);
      if (sum < minSum) {
        minSum = sum;
        minTeamIdx = t;
      }
    }
    (teams[minTeamIdx].members ??= []).push(user);
  }

  // Rebalance: try swapping users between teams to minimize max-min avg MMR
  const getAvg = (team: TeamType) => {
    const mmrs = (team.members ?? []).map((u: UserType) => u.mmr ?? 0);

    return mmrs.length ? mmrs.reduce((a: number, b: number) => a + b, 0) / mmrs.length : 0;
  };
  let improved = true;
  let maxIterations = 100;

  let curIteration = 0;
  while (improved && curIteration < maxIterations) {
    curIteration++;
    log.debug(`Iteration: ${curIteration}/ ${maxIterations}`);
    improved = false;
    // Find teams with max and min avg MMR
    let maxTeamIdx = 0,
      minTeamIdx = 0;
    let maxAvg = -Infinity,
      minAvg = Infinity;
    for (let t = 0; t < teams.length; t++) {
      const avg = getAvg(teams[t]);
      if (avg > maxAvg) {
        maxAvg = avg;
        maxTeamIdx = t;
      }
      if (avg < minAvg) {
        minAvg = avg;
        minTeamIdx = t;
      }
    }
    if (maxTeamIdx === minTeamIdx) break;

    // Try all swaps between max and min team
    const maxTeam = teams[maxTeamIdx];
    const minTeam = teams[minTeamIdx];
    const maxMembers = maxTeam.members ?? [];
    const minMembers = minTeam.members ?? [];
    let bestDelta = 0;
    let bestSwap: [number, number] | null = null;
    for (let i = 0; i < maxMembers.length; i++) {
      for (let j = 0; j < minMembers.length; j++) {
        const a = maxMembers[i];
        const b = minMembers[j];
        // Swap a and b, compute new avgs
        const maxTeamNew = [...maxMembers];
        const minTeamNew = [...minMembers];
        maxTeamNew[i] = b;
        minTeamNew[j] = a;
        const newMaxAvg =
          maxTeamNew.reduce((s, u) => s + (u.mmr ?? 0), 0) / maxTeamNew.length;
        const newMinAvg =
          minTeamNew.reduce((s, u) => s + (u.mmr ?? 0), 0) / minTeamNew.length;
        const oldDiff = Math.abs(maxAvg - minAvg);
        const newDiff = Math.abs(newMaxAvg - newMinAvg);
        if (newDiff < oldDiff - 0.01) {
          // Only accept real improvement
          const delta = oldDiff - newDiff;
          if (delta > bestDelta) {
            bestDelta = delta;
            bestSwap = [i, j];
          }
        }
      }

      log.debug(`bestSwap: ${bestSwap}, bestDelta: ${bestDelta}`);
    }
    log.debug(minMembers);
    if (bestSwap && maxTeam.members && minTeam.members) {
      // Perform the best swap directly on the teams' members arrayss
      const [i, j] = bestSwap;
      const temp = maxTeam.members[i];
      maxTeam.members[i] = minTeam.members[j];
      minTeam.members[j] = temp;
      improved = true;
    }
  }
  // Helper to create TeamType[] with members and captain (highest mmr or random)
  // Greedy algorithm to balance teams by total MMR (Karmarkar–Karp)

  // Assign captains (highest mmr or random if all mmr are null)
  teams.forEach((team) => {
    if ((team.members?.length ?? 0) > 0) {
      let captain = (team.members as UserType[]).reduce(
        (prev, curr) => ((curr.mmr ?? -1) > (prev.mmr ?? -1) ? curr : prev),
        (team.members as UserType[])[0],
      );
      if ((captain.mmr ?? null) === null) {
        captain = (team.members as UserType[])[
          Math.floor(Math.random() * (team.members as UserType[]).length)
        ];
      }
      team.captain = captain;
    }
  });
  // Only return teams with at least one member
  return teams;
}
