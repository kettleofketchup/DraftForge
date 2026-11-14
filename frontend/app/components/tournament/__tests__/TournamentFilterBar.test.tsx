// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { TournamentFilterBar, nextFilterParams } from '../TournamentFilterBar';

const orgState = vi.hoisted(() => ({ loading: false }));

vi.mock('~/components/organization', () => ({
  useOrganizations: () => ({
    organizations: orgState.loading
      ? []
      : [
          { pk: 30, name: 'Discovery Home' },
          { pk: 31, name: 'Discovery Away' },
          { pk: 32, name: 'Discovery Open' },
        ],
    isLoading: orgState.loading,
    refetch: vi.fn(),
  }),
}));

const leagueState = vi.hoisted(() => ({
  leagues: [{ pk: 31, name: 'Home League', organization: { pk: 30 } }] as Array<{
    pk: number;
    name: string;
    organization?: { pk: number } | null;
    organization_id?: number;
  }>,
}));

vi.mock('~/components/league', () => ({
  useLeagues: () => ({
    leagues: leagueState.leagues,
    isLoading: false,
    refetch: vi.fn(),
  }),
}));

const DEFAULT_LEAGUES = leagueState.leagues;

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
}

interface MembershipProps {
  isLoggedIn: boolean;
  memberOrgIds: number[] | undefined;
  membershipPending: boolean;
}

const LOGGED_OUT: MembershipProps = {
  isLoggedIn: false,
  memberOrgIds: undefined,
  membershipPending: false,
};
const MEMBER: MembershipProps = {
  isLoggedIn: true,
  memberOrgIds: [30],
  membershipPending: false,
};

function renderBar(
  initialEntry: string,
  searchInput = '',
  onSearchInputChange: (v: string) => void = vi.fn(),
  membership: MembershipProps = LOGGED_OUT,
) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/tournaments"
          element={
            <>
              <TournamentFilterBar
                searchInput={searchInput}
                onSearchInputChange={onSearchInputChange}
                {...membership}
              />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

function searchParamsShown(): URLSearchParams {
  return new URLSearchParams(screen.getByTestId('location-search').textContent ?? '');
}

afterEach(() => {
  orgState.loading = false;
  leagueState.leagues = DEFAULT_LEAGUES;
});

describe('TournamentFilterBar', () => {
  it('shows a loading placeholder for the organization while organizations load', () => {
    orgState.loading = true;
    renderBar('/tournaments?organization=30');
    const trigger = screen.getByRole('combobox', { name: /organization/i });
    expect(trigger).toHaveTextContent('Loading organizations…');
    expect(trigger).not.toHaveTextContent('Unknown organization');
  });

  it('shows Unknown organization for an organization outside the loaded list', () => {
    renderBar('/tournaments?organization=999');
    expect(screen.getByRole('combobox', { name: /organization/i })).toHaveTextContent(
      'Unknown organization',
    );
  });

  it('sizes the clear button to match the h-9 selects', () => {
    renderBar('/tournaments?organization=30');
    const clear = screen.getByTestId('tournaments-filter-clear');
    expect(clear).toHaveClass('h-9');
    expect(clear).not.toHaveClass('h-8');
  });

  it('renders a named search box and named org and league selects', () => {
    renderBar('/tournaments?tab=archived&organization=30');
    expect(screen.getByRole('textbox', { name: 'Search tournaments' })).toBeInTheDocument();
    expect(screen.getByTestId('tournaments-search')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /organization/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /league/i })).toBeInTheDocument();
  });

  it('forwards typed search text', () => {
    const onChange = vi.fn();
    renderBar('/tournaments', '', onChange);
    fireEvent.change(screen.getByRole('textbox', { name: 'Search tournaments' }), {
      target: { value: 'cup' },
    });
    expect(onChange).toHaveBeenCalledWith('cup');
  });

  it('shows the selected organization name in the trigger', () => {
    renderBar('/tournaments?organization=30');
    expect(screen.getByRole('combobox', { name: /organization/i })).toHaveTextContent(
      'Discovery Home',
    );
  });

  it('clear keeps tab and drops organization and search', () => {
    const onChange = vi.fn();
    renderBar('/tournaments?tab=archived&organization=30', '', onChange);
    fireEvent.click(screen.getByTestId('tournaments-filter-clear'));
    const params = searchParamsShown();
    expect(params.get('tab')).toBe('archived');
    expect(params.has('organization')).toBe(false);
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('hides clear for a one-character search with no params', () => {
    renderBar('/tournaments', 'a');
    expect(screen.queryByTestId('tournaments-filter-clear')).not.toBeInTheDocument();
  });

  it('ignores an invalid organization param', () => {
    renderBar('/tournaments?organization=abc');
    expect(screen.getByRole('combobox', { name: /organization/i })).toHaveTextContent(
      'All organizations',
    );
    expect(screen.queryByTestId('tournaments-filter-clear')).not.toBeInTheDocument();
  });

  it('shows Unknown league for a league outside the loaded list', () => {
    renderBar('/tournaments?organization=30&league=999');
    expect(screen.getByRole('combobox', { name: /league/i })).toHaveTextContent(
      'Unknown league',
    );
    expect(screen.getByTestId('tournaments-filter-clear')).toBeInTheDocument();
  });
});

beforeAll(() => {
  // Radix Select needs these pointer/scroll APIs, which jsdom lacks.
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

function openOrganizationSelect(): HTMLElement {
  const trigger = screen.getByRole('combobox', { name: /organization/i });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
  return screen.getByRole('listbox');
}

describe('TournamentFilterBar organization scope', () => {
  it('defaults to My organizations when logged in, without a clear button', () => {
    renderBar('/tournaments', '', vi.fn(), MEMBER);
    expect(screen.getByRole('combobox', { name: /organization/i })).toHaveTextContent(
      'My organizations',
    );
    expect(screen.queryByTestId('tournaments-filter-clear')).not.toBeInTheDocument();
  });

  it('lists My, All, then your and other organizations in groups', () => {
    renderBar('/tournaments', '', vi.fn(), MEMBER);
    const listbox = openOrganizationSelect();
    const options = within(listbox).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual([
      'My organizations',
      'All organizations',
      'Discovery Home',
      'Discovery Away',
      'Discovery Open',
    ]);
    const groups = within(listbox).getAllByRole('group');
    expect(groups.map((g) => within(g).getAllByRole('option').map((o) => o.textContent))).toEqual([
      ['Discovery Home'],
      ['Discovery Away', 'Discovery Open'],
    ]);
    expect(groups[0]).toHaveTextContent('Your organizations');
    expect(groups[1]).toHaveTextContent('Other organizations');
  });

  it('offers no My organizations option and no groups when logged out', () => {
    renderBar('/tournaments');
    expect(screen.getByRole('combobox', { name: /organization/i })).toHaveTextContent(
      'All organizations',
    );
    const listbox = openOrganizationSelect();
    expect(within(listbox).queryByText('My organizations')).toBeNull();
    expect(within(listbox).queryAllByRole('group')).toHaveLength(0);
    expect(within(listbox).getAllByRole('option')).toHaveLength(4);
  });

  it('writes organization=all and shows clear when a member picks All organizations', () => {
    renderBar('/tournaments?league=5', '', vi.fn(), MEMBER);
    const listbox = openOrganizationSelect();
    fireEvent.click(within(listbox).getByRole('option', { name: 'All organizations' }));
    const params = searchParamsShown();
    expect(params.get('organization')).toBe('all');
    expect(params.has('league')).toBe(false);
    expect(screen.getByTestId('tournaments-filter-clear')).toBeInTheDocument();
  });

  it('drops the param when a member picks My organizations again', () => {
    renderBar('/tournaments?organization=all', '', vi.fn(), MEMBER);
    const listbox = openOrganizationSelect();
    fireEvent.click(within(listbox).getByRole('option', { name: 'My organizations' }));
    expect(searchParamsShown().has('organization')).toBe(false);
  });

  it('shows a selected organization from a deep link when logged in', () => {
    renderBar('/tournaments?organization=31', '', vi.fn(), MEMBER);
    expect(screen.getByRole('combobox', { name: /organization/i })).toHaveTextContent(
      'Discovery Away',
    );
  });

  it('keeps the organization placeholder while membership resolves', () => {
    renderBar('/tournaments', '', vi.fn(), {
      isLoggedIn: false,
      memberOrgIds: undefined,
      membershipPending: true,
    });
    expect(screen.queryByRole('combobox', { name: /organization/i })).toBeNull();
    expect(screen.getByTestId('tournaments-filter-organization-pending')).toBeInTheDocument();
  });

  it('does not wait for membership on an explicit organization', () => {
    renderBar('/tournaments?organization=all', '', vi.fn(), {
      isLoggedIn: false,
      memberOrgIds: undefined,
      membershipPending: true,
    });
    expect(screen.getByRole('combobox', { name: /organization/i })).toHaveTextContent(
      'All organizations',
    );
  });

  it('clear returns a member to My organizations', () => {
    renderBar('/tournaments?organization=31', '', vi.fn(), MEMBER);
    fireEvent.click(screen.getByTestId('tournaments-filter-clear'));
    expect(searchParamsShown().has('organization')).toBe(false);
    expect(screen.getByRole('combobox', { name: /organization/i })).toHaveTextContent(
      'My organizations',
    );
  });
});

describe('nextFilterParams', () => {
  const base = () => new URLSearchParams('tab=archived&organization=30&league=31&x=1');

  it('changing organization sets it and drops league', () => {
    const input = base();
    const next = nextFilterParams(input, 'organization', '31');
    expect(next.get('organization')).toBe('31');
    expect(next.has('league')).toBe(false);
    expect(next.get('tab')).toBe('archived');
    expect(next.get('x')).toBe('1');
    expect(input.toString()).toBe('tab=archived&organization=30&league=31&x=1');
  });

  it('all organizations drops organization and league', () => {
    const next = nextFilterParams(base(), 'organization', 'all');
    expect(next.has('organization')).toBe(false);
    expect(next.has('league')).toBe(false);
    expect(next.get('tab')).toBe('archived');
    expect(next.get('x')).toBe('1');
  });

  it('all leagues drops only league', () => {
    const next = nextFilterParams(base(), 'league', 'all');
    expect(next.has('league')).toBe(false);
    expect(next.get('organization')).toBe('30');
  });

  it('for a member, mine drops organization and all is kept', () => {
    expect(nextFilterParams(base(), 'organization', 'mine', true).has('organization')).toBe(
      false,
    );
    expect(nextFilterParams(base(), 'organization', 'all', true).get('organization')).toBe(
      'all',
    );
  });

  it('changing league keeps organization', () => {
    const next = nextFilterParams(base(), 'league', '5');
    expect(next.get('league')).toBe('5');
    expect(next.get('organization')).toBe('30');
  });
});

describe('TournamentFilterBar leagues under My organizations', () => {
  function openLeagueSelect(): HTMLElement {
    const trigger = screen.getByRole('combobox', { name: /league/i });
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
    return screen.getByRole('listbox');
  }

  const MIXED = [
    { pk: 31, name: 'Home League', organization: { pk: 30 } },
    { pk: 32, name: 'Away League', organization: { pk: 31 } },
    { pk: 33, name: 'Staffed League', organization_id: 30 },
  ];

  it('lists only leagues of member organizations', () => {
    leagueState.leagues = MIXED;
    renderBar('/tournaments', '', vi.fn(), MEMBER);
    const options = within(openLeagueSelect()).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(['All leagues', 'Home League', 'Staffed League']);
  });

  it('lists every league under All organizations', () => {
    leagueState.leagues = MIXED;
    renderBar('/tournaments?organization=all', '', vi.fn(), MEMBER);
    const options = within(openLeagueSelect()).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(['All leagues', 'Home League', 'Away League', 'Staffed League']);
  });
});
