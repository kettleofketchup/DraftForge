// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { EntityContext } from '~/components/user/AddUserModal/types';
import { CSVImportModal } from './CSVImportModal';

const api = vi.hoisted(() => ({
  importCSVToOrg: vi.fn(),
  importCSVToTournament: vi.fn(),
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  importCSVToOrg: api.importCSVToOrg,
  importCSVToTournament: api.importCSVToTournament,
}));

vi.mock('./csvParser', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  parseCSV: vi.fn(async () => ({
    data: [{ steam_friend_id: '76561198012345678', mmr: '4200' }],
    errors: [],
  })),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

const emptyResult = {
  summary: { added: 1, created: 0, updated: 0, skipped: 0, errors: 0 },
  results: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.importCSVToOrg.mockResolvedValue(emptyResult);
  api.importCSVToTournament.mockResolvedValue(emptyResult);
});

async function toPreview(entityContext: EntityContext) {
  render(
    <CSVImportModal
      open
      onOpenChange={vi.fn()}
      entityContext={entityContext}
      onComplete={vi.fn()}
    />,
  );
  const drop = screen.getByText('Drop a CSV file here or click to browse');
  fireEvent.drop(drop, {
    dataTransfer: { files: [new File(['x'], 'users.csv')] },
  });
  await screen.findByText(/Import 1 rows/);
}

function choose(trigger: HTMLElement, option: string) {
  fireEvent.pointerDown(trigger, {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  fireEvent.click(screen.getByRole('option', { name: option }));
}

describe('CSVImportModal org MMR game', () => {
  it('org mode defaults the game to Dota 2 and sends game_type', async () => {
    await toPreview({ orgId: 4 });
    expect(screen.getByTestId('csv-game-select').textContent).toContain(
      'Dota 2',
    );
    fireEvent.click(screen.getByText(/Import 1 rows/));
    await waitFor(() => expect(api.importCSVToOrg).toHaveBeenCalled());
    expect(api.importCSVToOrg.mock.calls[0][2]).toMatchObject({
      game_type: 1,
    });
  });

  it('org mode sends the selected Deadlock game', async () => {
    await toPreview({ orgId: 4 });
    choose(screen.getByTestId('csv-game-select'), 'Deadlock');
    fireEvent.click(screen.getByText(/Import 1 rows/));
    await waitFor(() => expect(api.importCSVToOrg).toHaveBeenCalled());
    expect(api.importCSVToOrg.mock.calls[0][2]).toMatchObject({
      game_type: 2,
    });
  });

  it('tournament mode names the tournament game and hides the league target', async () => {
    await toPreview({ orgId: 4, tournamentId: 9, gameType: 2 });
    expect(screen.queryByTestId('csv-game-select')).toBeNull();
    expect(screen.getByTestId('csv-mmr-game-note').textContent).toBe(
      'MMR column applies to: Deadlock',
    );
    fireEvent.click(screen.getByText('Update MMR for existing members'));
    fireEvent.pointerDown(screen.getByLabelText('Store MMR in:'), {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
    expect(screen.queryByRole('option', { name: 'League' })).toBeNull();
    expect(screen.getByRole('option', { name: 'Organization' })).toBeTruthy();
  });

  it('tournament mode keeps the league target for Dota and sends no game_type', async () => {
    await toPreview({ orgId: 4, tournamentId: 9, gameType: 1 });
    expect(screen.getByTestId('csv-mmr-game-note').textContent).toBe(
      'MMR column applies to: Dota 2',
    );
    fireEvent.click(screen.getByText('Update MMR for existing members'));
    fireEvent.pointerDown(screen.getByLabelText('Store MMR in:'), {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
    expect(screen.getByRole('option', { name: 'League' })).toBeTruthy();
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    });
    fireEvent.click(screen.getByText(/Import 1 rows/));
    await waitFor(() => expect(api.importCSVToTournament).toHaveBeenCalled());
    expect(api.importCSVToTournament.mock.calls[0][2]).not.toHaveProperty(
      'game_type',
    );
  });
});
