// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { TournamentFilterBar, nextFilterParams } from '../TournamentFilterBar';

vi.mock('~/components/organization', () => ({
  useOrganizations: () => ({
    organizations: [
      { pk: 30, name: 'Discovery Home' },
      { pk: 31, name: 'Discovery Away' },
    ],
    isLoading: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('~/components/league', () => ({
  useLeagues: () => ({
    leagues: [{ pk: 31, name: 'Home League', organization: { pk: 30 } }],
    isLoading: false,
    refetch: vi.fn(),
  }),
}));

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
}

function renderBar(
  initialEntry: string,
  searchInput = '',
  onSearchInputChange: (v: string) => void = vi.fn(),
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

describe('TournamentFilterBar', () => {
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

  it('changing league keeps organization', () => {
    const next = nextFilterParams(base(), 'league', '5');
    expect(next.get('league')).toBe('5');
    expect(next.get('organization')).toBe('30');
  });
});
