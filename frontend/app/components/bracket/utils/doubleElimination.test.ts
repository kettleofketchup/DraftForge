import { describe, it, expect } from 'vitest';
import { generateDoubleElimination } from './doubleElimination';
import type { TeamType } from '~/components/tournament/types';

function buildTeams(n: number): TeamType[] {
  return Array.from({ length: n }, (_, i) => ({
    pk: i + 1,
    name: `Team ${i + 1}`,
  })) as unknown as TeamType[];
}

describe('generateDoubleElimination', () => {
  describe('8-team bracket structure', () => {
    const teams = buildTeams(8);
    const matches = generateDoubleElimination(teams);

    const byId = new Map(matches.map((m) => [m.id, m]));
    const losers = matches.filter((m) => m.bracketType === 'losers');
    const losersByRoundPos = new Map(
      losers.map((m) => [`l-${m.round}-${m.position}`, m]),
    );

    it('produces the expected number of matches per round', () => {
      const winners = matches.filter((m) => m.bracketType === 'winners');
      const gf = matches.filter((m) => m.bracketType === 'grand_finals');

      expect(winners.filter((m) => m.round === 1)).toHaveLength(4);
      expect(winners.filter((m) => m.round === 2)).toHaveLength(2);
      expect(winners.filter((m) => m.round === 3)).toHaveLength(1);

      expect(losers.filter((m) => m.round === 1)).toHaveLength(2);
      expect(losers.filter((m) => m.round === 2)).toHaveLength(2);
      expect(losers.filter((m) => m.round === 3)).toHaveLength(1);
      expect(losers.filter((m) => m.round === 4)).toHaveLength(1);

      expect(gf).toHaveLength(1);
    });

    it('routes both LB R2 winners into the single LB R3 match (minor → major)', () => {
      const lbR3Pos0 = losersByRoundPos.get('l-3-0')!;
      expect(lbR3Pos0).toBeDefined();

      const lbR2 = losers.filter((m) => m.round === 2);
      const targets = lbR2.map((m) => ({
        from: m.id,
        toId: m.nextMatchId,
        slot: m.nextMatchSlot,
      }));

      // Both LB R2 matches must feed into the single LB R3 match.
      for (const t of targets) {
        const dest = t.toId ? byId.get(t.toId) : undefined;
        expect(dest, `LB R2 ${t.from} -> ${t.toId} must exist`).toBeDefined();
        expect(dest!.bracketType).toBe('losers');
        expect(dest!.round).toBe(3);
        expect(dest!.position).toBe(0);
      }

      // Slots must be opposite — one radiant, one dire — so the single R3 match
      // ends up with two distinct teams.
      const slots = targets.map((t) => t.slot).sort();
      expect(slots).toEqual(['dire', 'radiant']);
    });

    it('does not route any LB R2 match into LB R4 (the WB-finals drop slot)', () => {
      const lbR4 = losersByRoundPos.get('l-4-0')!;
      const lbR2 = losers.filter((m) => m.round === 2);

      for (const m of lbR2) {
        const dest = m.nextMatchId ? byId.get(m.nextMatchId) : undefined;
        expect(dest?.id, `LB R2 ${m.id} must not skip to LB R4`).not.toBe(
          lbR4.id,
        );
      }
    });

    it('routes LB R3 winner to LB R4 radiant slot', () => {
      const lbR3 = losersByRoundPos.get('l-3-0')!;
      const lbR4 = losersByRoundPos.get('l-4-0')!;
      expect(lbR3.nextMatchId).toBe(lbR4.id);
      expect(lbR3.nextMatchSlot).toBe('radiant');
    });

    it('routes WB finals (R3) loser into LB R4 dire slot (does not collide with LB R3 winner)', () => {
      const winners = matches.filter((m) => m.bracketType === 'winners');
      const wbFinals = winners.find((m) => m.round === 3 && m.position === 0)!;
      const lbR4 = losersByRoundPos.get('l-4-0')!;
      expect(wbFinals.loserNextMatchId).toBe(lbR4.id);
      expect(wbFinals.loserNextMatchSlot).toBe('dire');
    });
  });

  describe('4-team bracket structure', () => {
    const teams = buildTeams(4);
    const matches = generateDoubleElimination(teams);
    const losers = matches.filter((m) => m.bracketType === 'losers');

    it('produces 2 LB matches (1 per round)', () => {
      expect(losers).toHaveLength(2);
      expect(losers.filter((m) => m.round === 1)).toHaveLength(1);
      expect(losers.filter((m) => m.round === 2)).toHaveLength(1);
    });

    it('routes LB R1 winner into LB R2 radiant slot', () => {
      const lbR1 = losers.find((m) => m.round === 1)!;
      const lbR2 = losers.find((m) => m.round === 2)!;
      expect(lbR1.nextMatchId).toBe(lbR2.id);
      expect(lbR1.nextMatchSlot).toBe('radiant');
    });
  });

  describe('16-team bracket structure', () => {
    const teams = buildTeams(16);
    const matches = generateDoubleElimination(teams);
    const losers = matches.filter((m) => m.bracketType === 'losers');
    const byId = new Map(matches.map((m) => [m.id, m]));
    const losersByRoundPos = new Map(
      losers.map((m) => [`l-${m.round}-${m.position}`, m]),
    );

    it('produces the expected LB shape (4,4,2,2,1,1)', () => {
      expect(losers.filter((m) => m.round === 1)).toHaveLength(4);
      expect(losers.filter((m) => m.round === 2)).toHaveLength(4);
      expect(losers.filter((m) => m.round === 3)).toHaveLength(2);
      expect(losers.filter((m) => m.round === 4)).toHaveLength(2);
      expect(losers.filter((m) => m.round === 5)).toHaveLength(1);
      expect(losers.filter((m) => m.round === 6)).toHaveLength(1);
    });

    it('routes every LB R2 match into a LB R3 match (no skipping)', () => {
      for (const m of losers.filter((x) => x.round === 2)) {
        const dest = m.nextMatchId ? byId.get(m.nextMatchId) : undefined;
        expect(dest, `${m.id} must have a next match`).toBeDefined();
        expect(dest!.bracketType).toBe('losers');
        expect(dest!.round).toBe(3);
      }
    });

    it('routes every LB R4 match into the single LB R5 match', () => {
      const lbR5 = losersByRoundPos.get('l-5-0')!;
      for (const m of losers.filter((x) => x.round === 4)) {
        expect(m.nextMatchId).toBe(lbR5.id);
      }
    });
  });
});
