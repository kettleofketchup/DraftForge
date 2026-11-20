import { describe, expect, it } from 'vitest';
import { TeamHistoryPageSchema } from '~/components/api/teamManagementAPI';
import {
  ghostCaptainDropoutTeam,
  ghostCaptainStandinTeam,
  managedTeam,
  people,
  richHistoryPage,
} from './fixtures';

describe('manage fixtures', () => {
  it('derive the intended shapes', () => {
    expect(managedTeam.members.map((m) => m.pk)).not.toContain(
      people.outsider.pk,
    );
    expect(ghostCaptainDropoutTeam.left_members).toContain(
      ghostCaptainDropoutTeam.captain,
    );
    expect(ghostCaptainStandinTeam.dropin_members).toContain(
      ghostCaptainStandinTeam.captain,
    );
    expect(TeamHistoryPageSchema.safeParse(richHistoryPage).success).toBe(true);
  });
});
