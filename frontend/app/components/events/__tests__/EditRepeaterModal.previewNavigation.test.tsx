// @vitest-environment jsdom
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { previewResponse } from '~/features/event-discord-preview/__tests__/fixtures';
import { createI18nInstance } from '~/i18n/config';
import { TestQueryClientProvider } from '~/test/TestQueryClientProvider';
import { EditRepeaterModal } from '../EditRepeaterModal';
import { baseRepeater } from './readyCheckModalFixtures';

const mocks = vi.hoisted(() => ({ preview: vi.fn(), mutateAsync: vi.fn() }));
vi.mock('~/features/event-discord-preview/api', () => ({
  previewEventDiscordMessage: mocks.preview,
}));
vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventRepeaterMutation: () => ({
    mutateAsync: mocks.mutateAsync,
    isPending: false,
  }),
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  fetchOrganization: vi.fn().mockResolvedValue(null),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
}));
vi.mock('~/components/lobby/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/lobby/api')>()),
  getRepeaterLobbyPassword: vi.fn().mockResolvedValue(null),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <TestQueryClientProvider>
      <I18nextProvider i18n={createI18nInstance('en')}>
        <TooltipProvider>{children}</TooltipProvider>
      </I18nextProvider>
    </TestQueryClientProvider>
  );
}

function selectTab(tab: 'event' | 'discord') {
  fireEvent.mouseDown(screen.getByTestId(`edit-series-tab-${tab}`), {
    button: 0,
  });
}

function renderSeries() {
  const onOpenChange = vi.fn();
  render(
    <EditRepeaterModal
      repeater={{ ...baseRepeater, frequency: 'daily', day_of_week: null }}
      open
      onOpenChange={onOpenChange}
    />,
    { wrapper: Wrapper },
  );
  return { onOpenChange };
}

async function openPreview() {
  fireEvent.click(screen.getByTestId('discord-preview-scheduled_event'));
  return screen.findByTestId('discord-preview-missing-schedule');
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.preview.mockResolvedValue(
    previewResponse({
      kind: 'scheduled_event',
      status: 'needs_input',
      missing: ['schedule'],
      messages: [],
      destination: null,
    }),
  );
});

describe('EditRepeaterModal preview navigation', () => {
  it('Schedule navigation preserves unsaved series and Discord edits', async () => {
    const { onOpenChange } = renderSeries();
    fireEvent.change(screen.getByTestId('edit-series-name-input'), {
      target: { value: 'Unsaved series name' },
    });
    const frequency = screen.getByTestId('edit-series-frequency-select');
    fireEvent.keyDown(frequency, { key: 'ArrowDown' });
    fireEvent.click(
      await screen.findByTestId('edit-series-frequency-option-weekly'),
    );
    expect(frequency).toHaveTextContent('Weekly');
    expect(screen.getByTestId('edit-series-day-select')).toHaveTextContent(
      'Select day',
    );

    selectTab('discord');
    fireEvent.click(screen.getByTestId('discord-discord_create_event'));
    fireEvent.change(screen.getByLabelText('Event title'), {
      target: { value: 'Unsaved Discord title' },
    });
    fireEvent.click(await openPreview());

    await waitFor(() => expect(frequency).toHaveFocus());
    expect(
      screen.queryByTestId('discord-preview-dialog'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('edit-series-modal')).toBeVisible();
    expect(screen.getByTestId('edit-series-tab-event')).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(frequency.closest('[data-search-hit]')).not.toBeNull();
    expect(screen.getByTestId('edit-series-name-input')).toHaveValue(
      'Unsaved series name',
    );
    expect(frequency).toHaveTextContent('Weekly');
    expect(screen.getByTestId('edit-series-day-select')).toHaveTextContent(
      'Select day',
    );

    selectTab('discord');
    expect(screen.getByLabelText('Event title')).toHaveValue(
      'Unsaved Discord title',
    );
    expect(screen.getByTestId('discord-discord_create_event')).toBeChecked();
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it.each(['Close', 'Escape'])(
    'ordinary preview dismissal with %s does not navigate',
    async (dismissal) => {
      const { onOpenChange } = renderSeries();
      selectTab('discord');
      await openPreview();
      const dialog = screen.getByTestId('discord-preview-dialog');
      if (dismissal === 'Close') {
        fireEvent.click(
          within(dialog).getByText('Close', { selector: 'button' }),
        );
      } else {
        fireEvent.keyDown(dialog, { key: 'Escape' });
      }
      await waitFor(() =>
        expect(
          screen.queryByTestId('discord-preview-dialog'),
        ).not.toBeInTheDocument(),
      );
      expect(screen.getByTestId('edit-series-modal')).toBeVisible();
      expect(screen.getByTestId('edit-series-tab-discord')).toHaveAttribute(
        'aria-selected',
        'true',
      );
      expect(
        screen
          .getByTestId('edit-series-frequency-select')
          .closest('[data-search-hit]'),
      ).toBeNull();
      expect(mocks.mutateAsync).not.toHaveBeenCalled();
      expect(onOpenChange).not.toHaveBeenCalled();
    },
  );
});
