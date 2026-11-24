// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { setViewportWidth } from '~/components/ui/data-table/__tests__/viewport';
import { PromotionTable, type PromotionTableProps } from '../PromotionTable';
import type { CandidateRow } from '../schemas';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

let restoreViewport: (() => void) | null = null;
afterEach(() => {
  restoreViewport?.();
  restoreViewport = null;
});

function row(overrides: Partial<CandidateRow>): CandidateRow {
  return {
    user_pk: 1,
    username: 'player',
    nickname: null,
    discordUsername: null,
    discordId: '100',
    avatarUrl: null,
    mmr: null,
    recent_count: 1,
    last_messaged: null,
    earning_send_exists: false,
    signed_up: false,
    ...overrides,
  };
}

const ana = row({
  user_pk: 11,
  username: 'ana',
  discordUsername: 'ana_dc',
  mmr: 3000,
  recent_count: 2,
});
const bo = row({
  user_pk: 12,
  username: 'bo',
  mmr: null,
  recent_count: 3,
  signed_up: true,
});
const cy = row({
  user_pk: 13,
  username: 'cy',
  mmr: 5200,
  recent_count: 1,
  last_messaged: {
    send_id: 90,
    by: 'promo_pal',
    sent_at: '2026-11-20T10:00:00Z',
    can_undo: true,
  },
});
const newbie = row({
  user_pk: null,
  username: 'newbie',
  discordId: '777',
  recent_count: null,
});

const preview = { locale: 'en', timeZone: 'UTC' };

function renderTable(props: Partial<PromotionTableProps> = {}) {
  const handlers = {
    onCompose: vi.fn(),
    onUndo: vi.fn(),
    onCopyHandle: vi.fn(),
  };
  render(
    <PromotionTable
      rows={[ana, bo, cy, newbie]}
      source="recent"
      poolN={3}
      previewOptions={preview}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

function rowIds(prefix = 'promo-candidate'): string[] {
  return screen
    .getAllByTestId(new RegExp(`^${prefix}-row-`))
    .map((el) => el.dataset.testid!.replace(`${prefix}-row-`, ''));
}

describe('PromotionTable', () => {
  it('keeps the server order by default', () => {
    renderTable();
    expect(rowIds()).toEqual(['11', '12', '13', 'discord-777']);
    expect(screen.getByTestId('promo-candidate-table')).toBeInTheDocument();
  });

  it('shows org MMR and Unknown, and sorts unknown last', () => {
    renderTable();
    expect(screen.getByTestId('promo-candidate-mmr-11')).toHaveTextContent(
      '3,000',
    );
    expect(screen.getByTestId('promo-candidate-mmr-12')).toHaveTextContent(
      'Unknown',
    );
    expect(
      screen.getByTestId('promo-candidate-mmr-discord-777'),
    ).toHaveTextContent('Unknown');
    fireEvent.click(screen.getByTestId('data-table-sort-mmr'));
    expect(rowIds()).toEqual(['13', '11', '12', 'discord-777']);
    fireEvent.click(screen.getByTestId('data-table-sort-mmr'));
    expect(rowIds().slice(0, 2)).toEqual(['11', '13']);
    expect(rowIds().slice(2).sort()).toEqual(['12', 'discord-777']);
  });

  it('stacks MMR, activity and status under the name for phones', () => {
    renderTable();
    expect(
      screen.getByTestId('promo-candidate-mmr-stacked-12'),
    ).toHaveTextContent('MMR Unknown');
    expect(
      screen.getByTestId('promo-candidate-stacked-badges-12'),
    ).toHaveTextContent('Signed up');
    const newbieRow = screen.getByTestId('promo-candidate-row-discord-777');
    expect(newbieRow).toHaveTextContent('No account yet');
    expect(screen.getByTestId('promo-candidate-row-11')).toHaveTextContent(
      'Played 2 of the last 3',
    );
  });

  it('renders a custom column list and test-id prefix', () => {
    renderTable({ columns: ['player', 'actions'], testIdPrefix: 'promo-x' });
    expect(screen.getByTestId('promo-x-table')).toBeInTheDocument();
    expect(rowIds('promo-x')).toHaveLength(4);
    expect(screen.queryByTestId('promo-x-mmr-11')).not.toBeInTheDocument();
    expect(screen.queryByTestId('data-table-sort-mmr')).not.toBeInTheDocument();
  });

  it('shows the empty message', () => {
    renderTable({ rows: [], emptyMessage: 'Nobody here' });
    expect(screen.getByText('Nobody here')).toBeInTheDocument();
  });

  it('inline actions from md: message, mark as sent, undo only where allowed', () => {
    restoreViewport = setViewportWidth(1280);
    const { onCompose, onUndo } = renderTable();
    const group = screen.getByTestId('promo-candidate-actions-13');
    expect(group).toHaveAttribute('role', 'group');
    fireEvent.click(within(group).getByTestId('promo-candidate-message-13'));
    expect(onCompose).toHaveBeenCalledWith(cy, 'message');
    fireEvent.click(within(group).getByTestId('promo-candidate-record-13'));
    expect(onCompose).toHaveBeenCalledWith(cy, 'record');
    fireEvent.click(within(group).getByTestId('promo-candidate-undo-13'));
    expect(onUndo).toHaveBeenCalledWith(90);
    expect(
      screen.queryByTestId('promo-candidate-undo-11'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('promo-last-messaged-13')).toHaveTextContent(
      'Messaged by promo_pal',
    );
  });

  it('hides the row undo for the send owned by the open composer', () => {
    restoreViewport = setViewportWidth(1280);
    renderTable({ hideUndoFor: 90 });
    expect(
      screen.queryByTestId('promo-candidate-undo-13'),
    ).not.toBeInTheDocument();
  });

  it('disables a pending row while its account is prepared', () => {
    restoreViewport = setViewportWidth(1280);
    const { onCompose } = renderTable({ pendingRowId: 'discord-777' });
    const message = screen.getByTestId('promo-candidate-message-discord-777');
    expect(message).toBeDisabled();
    expect(message).toHaveTextContent('Preparing...');
    expect(
      screen.getByTestId('promo-candidate-record-discord-777'),
    ).toBeDisabled();
    fireEvent.click(message);
    expect(onCompose).not.toHaveBeenCalled();
    expect(screen.getByTestId('promo-candidate-message-11')).toBeEnabled();
  });

  it('disables undo while an undo is pending', () => {
    restoreViewport = setViewportWidth(1280);
    renderTable({ undoPending: true });
    expect(screen.getByTestId('promo-candidate-undo-13')).toBeDisabled();
  });

  it('below md the actions are a menu only', async () => {
    const { onCompose } = renderTable();
    expect(
      screen.queryByTestId('promo-candidate-message-11'),
    ).not.toBeInTheDocument();
    const trigger = screen.getByTestId('promo-candidate-actions-11');
    expect(trigger).toHaveAccessibleName('Actions for ana');
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
    fireEvent.click(await screen.findByTestId('promo-candidate-record-11'));
    expect(onCompose).toHaveBeenCalledWith(ana, 'record');
  });

  it('copies the Discord handle without other actions', () => {
    const { onCopyHandle, onCompose } = renderTable();
    fireEvent.click(screen.getByTestId('promo-copy-discord-11'));
    expect(onCopyHandle).toHaveBeenCalledWith('ana_dc');
    expect(onCompose).not.toHaveBeenCalled();
  });
});
