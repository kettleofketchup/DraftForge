// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { getDiscordChannels, type DiscordChannel } from '~/components/api/api';
import { DiscordChannelPicker } from '../DiscordChannelPicker';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getDiscordChannels: vi.fn(),
}));

const mockedGetChannels = vi.mocked(getDiscordChannels);

const TEXT: DiscordChannel[] = [
  { id: '1', name: 'general', type: 0, type_label: 'text' },
];
const VOICE: DiscordChannel[] = [
  { id: '2', name: 'Lobby Voice', type: 2, type_label: 'voice' },
];

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

beforeEach(() => {
  mockedGetChannels.mockReset();
});

function openSelect(): HTMLElement {
  const trigger = screen.getByTestId('picker');
  fireEvent.pointerDown(trigger, {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  return screen.getByRole('listbox');
}

describe('DiscordChannelPicker kind', () => {
  it('requests voice channels for kind="voice"', async () => {
    mockedGetChannels.mockResolvedValue(VOICE);
    render(
      <DiscordChannelPicker
        organizationId={7}
        value=""
        onChange={vi.fn()}
        kind="voice"
        data-testid="picker"
      />,
    );
    await waitFor(() =>
      expect(mockedGetChannels).toHaveBeenCalledWith(7, false, 'voice'),
    );
  });

  it('defaults to text channels', async () => {
    mockedGetChannels.mockResolvedValue(TEXT);
    render(
      <DiscordChannelPicker
        organizationId={7}
        value=""
        onChange={vi.fn()}
        data-testid="picker"
      />,
    );
    await waitFor(() =>
      expect(mockedGetChannels).toHaveBeenCalledWith(7, false, 'text'),
    );
  });

  it.each([
    ['voice', 'No voice channels found'],
    ['text', 'No text channels found'],
  ] as const)('empty %s list shows "%s"', async (kind, message) => {
    mockedGetChannels.mockResolvedValue([]);
    render(
      <DiscordChannelPicker
        organizationId={7}
        value=""
        onChange={vi.fn()}
        kind={kind}
        data-testid="picker"
      />,
    );
    await waitFor(() => expect(screen.getByTestId('picker')).toBeEnabled());
    openSelect();
    expect(screen.getByText(message)).toBeInTheDocument();
  });

  it('switching text to voice refetches and never shows the text channel', async () => {
    mockedGetChannels.mockResolvedValueOnce(TEXT);
    const { rerender } = render(
      <DiscordChannelPicker
        organizationId={7}
        value="1"
        onChange={vi.fn()}
        kind="text"
        data-testid="picker"
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('picker')).toHaveTextContent('general'),
    );

    let resolveVoice: (value: DiscordChannel[]) => void = () => undefined;
    mockedGetChannels.mockReturnValueOnce(
      new Promise<DiscordChannel[]>((resolve) => {
        resolveVoice = resolve;
      }),
    );
    rerender(
      <DiscordChannelPicker
        organizationId={7}
        value="1"
        onChange={vi.fn()}
        kind="voice"
        data-testid="picker"
      />,
    );
    expect(screen.queryByText('general')).not.toBeInTheDocument();
    expect(mockedGetChannels).toHaveBeenLastCalledWith(7, false, 'voice');

    await act(async () => resolveVoice(VOICE));
    await waitFor(() => expect(screen.getByTestId('picker')).toBeEnabled());
    const listbox = openSelect();
    expect(listbox).toHaveTextContent('Lobby Voice');
    expect(screen.queryByText('general')).not.toBeInTheDocument();
  });

  it('ignores a text response that arrives after switching to voice', async () => {
    let resolveText: (value: DiscordChannel[]) => void = () => undefined;
    mockedGetChannels.mockReturnValueOnce(
      new Promise<DiscordChannel[]>((resolve) => {
        resolveText = resolve;
      }),
    );
    mockedGetChannels.mockResolvedValueOnce(VOICE);
    const { rerender } = render(
      <DiscordChannelPicker
        organizationId={7}
        value=""
        onChange={vi.fn()}
        kind="text"
        data-testid="picker"
      />,
    );
    rerender(
      <DiscordChannelPicker
        organizationId={7}
        value=""
        onChange={vi.fn()}
        kind="voice"
        data-testid="picker"
      />,
    );
    await waitFor(() => expect(screen.getByTestId('picker')).toBeEnabled());
    await act(async () => resolveText(TEXT));
    const listbox = openSelect();
    expect(listbox).toHaveTextContent('Lobby Voice');
    expect(screen.queryByText('general')).not.toBeInTheDocument();
  });
});
