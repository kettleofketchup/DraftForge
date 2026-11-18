// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { OpsNotice } from '~/components/api/opsNoticesAPI';
import { OpsNoticeTable, type OpsNoticeTableProps } from '../OpsNoticeTable';

function makeNotice(overrides: Partial<OpsNotice>): OpsNotice {
  return {
    id: 1,
    key: 'test.alert',
    label: 'Test alert',
    category: 'urgent',
    severity: 'critical',
    state: 'open',
    summary: 'Lobby bot is offline',
    event_id: 11,
    event_name: 'Night 4',
    subject_user: null,
    actor: null,
    dedupe_key: '',
    occurrences: 1,
    first_seen_at: '2026-11-18T10:00:00Z',
    last_seen_at: '2026-11-18T10:00:00Z',
    closed_at: null,
    close_note: '',
    delivery_state: 'pending',
    payload: {},
    ...overrides,
  };
}

const info = makeNotice({
  id: 1,
  category: 'task',
  severity: 'info',
  summary: 'Check in late players',
  last_seen_at: '2026-11-18T12:00:00Z',
});
const warnOld = makeNotice({
  id: 2,
  severity: 'warning',
  summary: 'Reminder undelivered',
  last_seen_at: '2026-11-18T09:00:00Z',
});
const warnNew = makeNotice({
  id: 3,
  severity: 'warning',
  summary: 'Role sync slow',
  last_seen_at: '2026-11-18T11:00:00Z',
});
const critical = makeNotice({ id: 4, occurrences: 3 });

function renderTable(props: Partial<OpsNoticeTableProps> = {}) {
  return render(
    <MemoryRouter>
      <OpsNoticeTable notices={[info, warnOld, warnNew, critical]} {...props} />
    </MemoryRouter>,
  );
}

function rowIds(): string[] {
  return screen
    .getAllByTestId(/^ops-notice-row-/)
    .map((r) => r.getAttribute('data-testid') ?? '');
}

afterEach(cleanup);

describe('OpsNoticeTable', () => {
  it('orders by severity, then most recently seen', () => {
    renderTable();
    expect(rowIds()).toEqual([
      'ops-notice-row-4',
      'ops-notice-row-3',
      'ops-notice-row-2',
      'ops-notice-row-1',
    ]);
  });

  it('shows the event column by default and drops it from a custom column list', () => {
    renderTable();
    expect(
      screen.getByRole('columnheader', { name: 'Event' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('ops-notice-row-4')).toHaveTextContent('Night 4');
    cleanup();
    renderTable({
      columns: ['severity', 'summary', 'last_seen', 'actions'],
      onResolve: vi.fn(),
    });
    expect(screen.queryByRole('columnheader', { name: 'Event' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: 'Type' })).toBeNull();
    expect(screen.getByTestId('ops-notice-row-4')).not.toHaveTextContent(
      'Night 4',
    );
  });

  it('namespaces test ids with testIdPrefix', () => {
    renderTable({ testIdPrefix: 'org-notices', onResolve: vi.fn() });
    expect(screen.getByTestId('org-notices-table')).toBeInTheDocument();
    expect(screen.getByTestId('org-notices-row-4')).toBeInTheDocument();
    expect(screen.getByTestId('org-notices-resolve-4')).toBeInTheDocument();
  });

  it('stacks type and age under the notice for small screens', () => {
    renderTable();
    const summary = within(screen.getByTestId('ops-notice-row-1')).getByText(
      'Check in late players',
    );
    expect(summary.parentElement).toHaveTextContent(/task ·/);
  });

  it('resolving does not trigger the row click', () => {
    const onResolve = vi.fn();
    const onRowClick = vi.fn();
    renderTable({ onResolve, onRowClick });
    fireEvent.click(screen.getByTestId('ops-notice-resolve-4'));
    expect(onResolve).toHaveBeenCalledWith(critical);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('turns header sorting off with sortable=false', () => {
    renderTable({ sortable: false });
    expect(screen.queryByTestId('data-table-sort-last_seen')).toBeNull();
    expect(screen.queryByTestId('data-table-sort-severity')).toBeNull();
  });

  it('shows the occurrence count only above one', () => {
    renderTable();
    expect(screen.getByTestId('ops-notice-row-4')).toHaveTextContent('x3');
    expect(screen.getByTestId('ops-notice-row-2')).not.toHaveTextContent('x1');
  });

  it('offers Resolve on urgent rows only, when onResolve is given', () => {
    const onResolve = vi.fn();
    renderTable({ onResolve });
    expect(screen.queryByTestId('ops-notice-resolve-1')).toBeNull();
    fireEvent.click(screen.getByTestId('ops-notice-resolve-4'));
    expect(onResolve).toHaveBeenCalledWith(critical);
  });

  it('has no actions column without onResolve', () => {
    renderTable();
    expect(screen.queryByTestId('ops-notice-resolve-4')).toBeNull();
  });

  it('disables Resolve while a resolve is in flight', () => {
    renderTable({ onResolve: vi.fn(), resolving: true });
    expect(screen.getByTestId('ops-notice-resolve-4')).toBeDisabled();
  });

  it('re-sorts when a sortable header is clicked', () => {
    renderTable();
    const btn = screen.getByTestId('data-table-sort-last_seen');
    fireEvent.click(btn);
    expect(rowIds()).toEqual([
      'ops-notice-row-1',
      'ops-notice-row-3',
      'ops-notice-row-4',
      'ops-notice-row-2',
    ]);
    fireEvent.click(btn);
    expect(rowIds()[0]).toBe('ops-notice-row-2');
  });

  it('shows the empty message with no notices', () => {
    render(
      <MemoryRouter>
        <OpsNoticeTable notices={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByText('No open notices')).toBeInTheDocument();
  });
});
