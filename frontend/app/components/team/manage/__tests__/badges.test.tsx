// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';

import { TooltipProvider } from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { LeadershipProblemBadge } from '../LeadershipProblemBadge';
import { RosterStatusBadge } from '../RosterStatusBadge';
import { ghostCaptainTeam, ghostDeputyTeam, managedTeam } from './fixtures';

function renderWithTooltips(ui: ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

const ROSTER_STATUSES = [
  ['captain', 'Captain'],
  ['deputy', 'Deputy'],
  ['standin', 'Stand-in'],
  ['dropout', 'Dropout'],
] as const;

const RAW_PALETTE =
  /\b(?:bg|text|border)-(?:red|green|blue|purple|violet|emerald|rose|orange|amber|cyan|teal)-\d/;

describe('RosterStatusBadge', () => {
  it.each(ROSTER_STATUSES)('renders %s as "%s"', (status, text) => {
    render(<RosterStatusBadge status={status} />);
    expect(screen.getByTestId(`roster-status-${status}`)).toHaveTextContent(
      text,
    );
  });

  it.each(ROSTER_STATUSES)(
    'gives %s the shared size and a token tone',
    (status) => {
      render(<RosterStatusBadge status={status} />);
      const badge = screen.getByTestId(`roster-status-${status}`);
      for (const cls of ['text-[10px]', 'px-1.5', 'py-0']) {
        expect(badge).toHaveClass(cls);
      }
      expect(badge.className).not.toMatch(RAW_PALETTE);
    },
  );

  it('gives each status its own tone', () => {
    render(
      <>
        {ROSTER_STATUSES.map(([status]) => (
          <RosterStatusBadge key={status} status={status} />
        ))}
      </>,
    );
    const classes = ROSTER_STATUSES.map(
      ([status]) => screen.getByTestId(`roster-status-${status}`).className,
    );
    expect(new Set(classes).size).toBe(ROSTER_STATUSES.length);
  });
});

describe('LeadershipProblemBadge', () => {
  it('renders nothing without problems', () => {
    const { container } = renderWithTooltips(
      <LeadershipProblemBadge problems={[]} team={managedTeam} />,
    );
    expect(container.innerHTML).toBe('');
    expect(screen.queryByTestId('team-leadership-problem')).toBeNull();
  });

  it('labels the badge with the named problem', () => {
    renderWithTooltips(
      <LeadershipProblemBadge
        problems={ghostCaptainTeam.leadership_problems}
        team={ghostCaptainTeam}
      />,
    );
    const badge = screen.getByTestId('team-leadership-problem');
    expect(badge.getAttribute('aria-label')).toContain(
      `${DisplayName(ghostCaptainTeam.captain!)} is not a member of this team.`,
    );
  });

  it('lists every problem in the label', () => {
    const team = {
      ...ghostDeputyTeam,
      leadership_problems: [
        ...ghostDeputyTeam.leadership_problems,
        ...ghostCaptainTeam.leadership_problems,
      ],
    };
    renderWithTooltips(
      <LeadershipProblemBadge
        problems={team.leadership_problems}
        team={team}
      />,
    );
    const label =
      screen
        .getByTestId('team-leadership-problem')
        .getAttribute('aria-label') ?? '';
    expect(label).toContain(
      `${DisplayName(team.deputy_captain!)} is not a member of this team.`,
    );
    expect(label).toContain(
      `${DisplayName(team.captain!)} is not a member of this team.`,
    );
  });

  it('falls back to the server message for an unknown code', () => {
    renderWithTooltips(
      <LeadershipProblemBadge
        problems={[{ code: 'future_code', message: 'Something is off.' }]}
        team={managedTeam}
      />,
    );
    expect(
      screen.getByTestId('team-leadership-problem').getAttribute('aria-label'),
    ).toContain('Something is off.');
  });
});
