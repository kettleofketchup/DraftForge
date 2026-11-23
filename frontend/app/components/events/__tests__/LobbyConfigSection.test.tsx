// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { beforeAll, describe, expect, it } from 'vitest';

import { GAME_TYPE } from '~/components/game/constants';
import { Form } from '~/components/ui/form';
import { LobbyConfigSection } from '../LobbyConfigSection';
import { GameMode } from '../schemas';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

type LobbyFields = {
  game_type: number;
  game_mode: string;
  lobby_steam_league_id: number | null;
  captains_draft_time: number;
  custom_game_name: string;
};

const DEFAULTS: LobbyFields = {
  game_type: GAME_TYPE.DOTA2,
  game_mode: GameMode.NORMAL,
  lobby_steam_league_id: null,
  captains_draft_time: 30,
  custom_game_name: '',
};

let form: UseFormReturn<LobbyFields>;

function Harness({ initial }: { initial: Partial<LobbyFields> }) {
  form = useForm<LobbyFields>({ defaultValues: { ...DEFAULTS, ...initial } });
  return (
    <Form {...form}>
      <LobbyConfigSection control={form.control} />
    </Form>
  );
}

function renderSection(initial: Partial<LobbyFields> = {}) {
  render(<Harness initial={initial} />);
}

const gameMode = () => screen.getByRole('combobox', { name: 'Game Mode' });
const leagueId = () => screen.queryByLabelText('Steam League ID');
const draftTime = () => screen.queryByLabelText('Draft Time (seconds)');
const customName = () => screen.queryByLabelText('Custom Game Name');

function openGameMode() {
  fireEvent.pointerDown(gameMode(), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

function chooseGameMode(label: string) {
  openGameMode();
  fireEvent.click(screen.getByRole('option', { name: label }));
}

const type = (el: HTMLElement | null, value: string) => {
  fireEvent.change(el!, { target: { value } });
};

describe('LobbyConfigSection', () => {
  it('renders the Dota fields with the form values', () => {
    renderSection({ lobby_steam_league_id: 17411 });
    expect(screen.getByText('Game lobby')).toBeInTheDocument();
    expect(gameMode()).toHaveTextContent('Normal');
    expect(gameMode()).toHaveAttribute('data-testid', 'lobby-config-game-mode');
    expect(leagueId()).toHaveValue(17411);
    expect(leagueId()).toHaveAttribute('placeholder', 'Optional');
    expect(draftTime()).toBeNull();
    expect(customName()).toBeNull();
  });

  it('renders an empty Steam League ID when the form value is null', () => {
    renderSection();
    expect(leagueId()).toHaveValue(null);
    expect(leagueId()).toHaveDisplayValue('');
  });

  it('offers every game mode for Dota 2', () => {
    renderSection();
    openGameMode();
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Normal',
      "Captain's Mode",
      'Turbo',
      'Custom Lobby',
    ]);
  });

  it('hides Dota-only modes and the Steam League ID for other games', () => {
    renderSection({
      game_type: GAME_TYPE.DEADLOCK,
      lobby_steam_league_id: 17411,
    });
    expect(leagueId()).toBeNull();
    openGameMode();
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Normal',
      'Custom Lobby',
    ]);
  });

  it('reacts when the game type changes after render', () => {
    renderSection();
    expect(leagueId()).toBeInTheDocument();
    act(() => form.setValue('game_type', GAME_TYPE.DEADLOCK));
    expect(leagueId()).toBeNull();
    act(() => form.setValue('game_type', GAME_TYPE.DOTA2));
    expect(leagueId()).toBeInTheDocument();
  });

  it.each([
    ["Captain's Mode", GameMode.CAPTAINS_MODE],
    ['Turbo', GameMode.TURBO],
    ['Custom Lobby', GameMode.CUSTOM],
    ['Normal', GameMode.NORMAL],
  ])('picking %s writes %s', (label, value) => {
    renderSection({ game_mode: GameMode.TURBO });
    chooseGameMode(label);
    expect(form.getValues('game_mode')).toBe(value);
    expect(gameMode()).toHaveTextContent(label);
  });

  it('writes the Steam League ID as a number, and null when cleared', () => {
    renderSection();
    type(leagueId(), '17411');
    expect(form.getValues('lobby_steam_league_id')).toBe(17411);
    expect(leagueId()).toHaveValue(17411);
    type(leagueId(), '');
    expect(form.getValues('lobby_steam_league_id')).toBeNull();
    expect(leagueId()).toHaveDisplayValue('');
  });

  it("shows Draft Time only in Captain's Mode", () => {
    renderSection({ captains_draft_time: 45 });
    expect(draftTime()).toBeNull();
    chooseGameMode("Captain's Mode");
    expect(draftTime()).toHaveValue(45);
    expect(draftTime()).toHaveAttribute('min', '1');
    expect(
      screen.getByText("Seconds per pick in Captain's Mode draft"),
    ).toBeInTheDocument();
    expect(customName()).toBeNull();
    chooseGameMode('Normal');
    expect(draftTime()).toBeNull();
  });

  it('writes Draft Time as a number, clamped to at least 1 on blur', () => {
    renderSection({ game_mode: GameMode.CAPTAINS_MODE });
    type(draftTime(), '25');
    expect(form.getValues('captains_draft_time')).toBe(25);
    type(draftTime(), '0');
    expect(form.getValues('captains_draft_time')).toBe(25);
    fireEvent.blur(draftTime()!);
    expect(form.getValues('captains_draft_time')).toBe(1);
    expect(draftTime()).toHaveValue(1);
  });

  it('keeps Draft Time empty while editing and restores it on blur', () => {
    renderSection({
      game_mode: GameMode.CAPTAINS_MODE,
      captains_draft_time: 30,
    });
    type(draftTime(), '');
    expect(draftTime()).toHaveValue(null);
    expect(form.getValues('captains_draft_time')).toBe(30);
    fireEvent.blur(draftTime()!);
    expect(draftTime()).toHaveValue(30);
  });

  it('shows Custom Game Name only for a custom lobby and writes it', () => {
    renderSection({ custom_game_name: 'Dota 12v12' });
    expect(customName()).toBeNull();
    chooseGameMode('Custom Lobby');
    expect(customName()).toHaveValue('Dota 12v12');
    expect(customName()).toHaveAttribute('placeholder', 'e.g. Dota 12v12');
    expect(draftTime()).toBeNull();
    type(customName(), 'Overthrow');
    expect(form.getValues('custom_game_name')).toBe('Overthrow');
  });

  it('shows Custom Game Name for a custom lobby in other games too', () => {
    renderSection({
      game_type: GAME_TYPE.DEADLOCK,
      game_mode: GameMode.CUSTOM,
    });
    expect(gameMode()).toHaveTextContent('Custom Lobby');
    expect(customName()).toBeInTheDocument();
    expect(leagueId()).toBeNull();
  });
});
