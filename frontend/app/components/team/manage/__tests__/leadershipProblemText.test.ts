import { describe, expect, it } from 'vitest';
import { leadershipProblemParts } from '../leadershipProblemText';
import {
  ghostCaptainTeam,
  ghostDeputyTeam,
  managedTeam,
  people,
} from './fixtures';

describe('leadershipProblemParts', () => {
  it('names the captain for captain_not_member', () => {
    const parts = leadershipProblemParts(
      ghostCaptainTeam.leadership_problems[0],
      ghostCaptainTeam,
    );
    expect(parts).toEqual({
      subject: ghostCaptainTeam.captain,
      text: 'is not a member of this team.',
    });
  });

  it('names the deputy for deputy_not_member', () => {
    const parts = leadershipProblemParts(
      ghostDeputyTeam.leadership_problems[0],
      ghostDeputyTeam,
    );
    expect(parts).toEqual({
      subject: people.outsider,
      text: 'is not a member of this team.',
    });
  });

  it('names the deputy for deputy_is_captain', () => {
    const team = { ...managedTeam, deputy_captain: people.captain };
    const parts = leadershipProblemParts(
      {
        field: 'deputy_captain',
        code: 'deputy_is_captain',
        message: 'Deputy captain cannot be the same as captain.',
      },
      team,
    );
    expect(parts).toEqual({
      subject: people.captain,
      text: 'is also the captain.',
    });
  });

  it('falls back to the server message for an unknown code', () => {
    const parts = leadershipProblemParts(
      { field: 'captain', code: 'something_new', message: 'Server says no.' },
      managedTeam,
    );
    expect(parts).toEqual({ subject: null, text: 'Server says no.' });
  });

  it('has no subject when the field is empty', () => {
    const parts = leadershipProblemParts(
      ghostCaptainTeam.leadership_problems[0],
      { ...ghostCaptainTeam, captain: null },
    );
    expect(parts.subject).toBeNull();
    expect(parts.text).toBe('is not a member of this team.');
  });
});
