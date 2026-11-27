// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { useForm } from 'react-hook-form';
import { I18nextProvider, setI18n } from 'react-i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Form } from '~/components/ui/form';
import { createI18nInstance, FALLBACK_LOCALE } from '~/i18n/config';
import { TestQueryClientProvider } from '~/test/TestQueryClientProvider';
import type { DiscordPreviewContext } from '../context';
import { EventDiscordPreviewButton } from '../EventDiscordPreviewButton';
import { EventPreviewBody } from '../EventPreviewBody';
import { previewResponse } from './fixtures';

const mocks = vi.hoisted(() => ({
  preview: vi.fn(),
  roles: vi.fn(),
  channels: vi.fn(),
}));

vi.mock('../api', () => ({ previewEventDiscordMessage: mocks.preview }));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getDiscordRoles: mocks.roles,
  getDiscordChannels: mocks.channels,
}));

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset());
  mocks.roles.mockResolvedValue([{ id: '111', name: 'Inhouse', color: 0 }]);
  mocks.channels.mockResolvedValue([
    { id: '1234', name: 'event-signups' },
    { id: '5678', name: 'announcements' },
  ]);
  mocks.preview.mockResolvedValue(previewResponse());
});

afterEach(() => {
  setI18n(createI18nInstance(FALLBACK_LOCALE));
});

function FormHarness({
  children,
  values,
}: {
  children: ReactNode;
  values: Record<string, unknown>;
}) {
  const form = useForm<Record<string, unknown>>({ defaultValues: values });
  return <Form {...form}>{children}</Form>;
}

function renderButton(
  context: DiscordPreviewContext | undefined,
  kind: Parameters<typeof EventDiscordPreviewButton>[0]['kind'] = 'signup_post',
  values: Record<string, unknown> = {
    name: 'Friday Inhouse',
    timezone: 'UTC',
    scheduled_at: '2026-12-04T18:00',
    signup_open_mode: 'immediate',
    dota_lobby_password: 'secret12',
  },
) {
  return render(
    <TestQueryClientProvider>
      <FormHarness values={values}>
        <EventDiscordPreviewButton
          kind={kind}
          organizationId={7}
          context={context}
        />
      </FormHarness>
    </TestQueryClientProvider>,
  );
}

async function openDialog(kind = 'signup_post') {
  fireEvent.click(screen.getByTestId(`discord-preview-${kind}`));
  const dialog = await screen.findByTestId('discord-preview-dialog');
  return dialog;
}

describe('EventDiscordPreviewButton', () => {
  it.each([
    ['en', 'See how this will appear in Discord.', 'No channel selected.'],
    ['es', 'Así se verá en Discord.', 'No se ha seleccionado ningún canal.'],
  ] as const)(
    'uses natural %s subtitle and no-channel wording',
    async (locale, subtitle, destination) => {
      const i18n = createI18nInstance(locale);
      render(
        <I18nextProvider i18n={i18n}>
          <TestQueryClientProvider>
            <EventDiscordPreviewButton kind="signup_post" organizationId={7} />
            <EventPreviewBody
              organizationId={7}
              data={previewResponse({
                destination: {
                  type: 'channel',
                  channel_id: null,
                  thread_name: null,
                  fallback_channel_id: null,
                  reply_to_message_id: null,
                },
              })}
            />
          </TestQueryClientProvider>
        </I18nextProvider>,
      );
      await openDialog();
      expect(
        screen.getByTestId('discord-preview-dialog'),
      ).toHaveAccessibleDescription(subtitle);
      expect(
        screen.getByTestId('discord-preview-destination').textContent,
      ).toBe(destination);
    },
  );

  it.each(['t', 'T', 'd', 'D', 'f', 'F', 'R'])(
    'renders %s timestamps in the no-recipients header',
    async (style) => {
      mocks.preview.mockResolvedValue(
        previewResponse({
          kind: 'start_mention',
          gate: { would_send: false, reasons: ['no_recipients'] },
          messages: [],
          note_args: {
            header: `Friday Inhouse starts <t:1796261040:${style}>!`,
          },
        }),
      );
      renderButton({ type: 'event', eventId: 42 }, 'start_mention');
      const dialog = await openDialog('start_mention');
      const box = await within(dialog).findByTestId(
        'discord-preview-start-mention-header',
      );
      expect(box.textContent).not.toContain('<t:');
      expect(box.querySelector('time')).toHaveAttribute(
        'datetime',
        new Date(1796261040 * 1000).toISOString(),
      );
      expect(box.querySelector('time')?.textContent).not.toBe('');
    },
  );
  it.each([
    [
      { type: 'event', eventId: 42 },
      { type: 'event', event_id: 42 },
    ],
    [
      { type: 'new_event', organizationId: 7 },
      { type: 'new_event', organization_id: 7 },
    ],
    [
      { type: 'series_one_off', repeaterId: 3 },
      { type: 'series_one_off', repeater_id: 3 },
    ],
    [
      { type: 'repeater', repeaterId: 3 },
      { type: 'repeater', repeater_id: 3 },
    ],
    [
      { type: 'new_repeater', organizationId: 7 },
      { type: 'new_repeater', organization_id: 7 },
    ],
  ] as const)('posts context %o as %o', async (context, api) => {
    renderButton(context);
    await openDialog();
    await screen.findByTestId('discord-message-preview');
    const req = mocks.preview.mock.calls[0][0];
    expect(req.context).toEqual(api);
    expect(req.kind).toBe('signup_post');
    expect(req.open_signups).toBe(true);
    expect(req.values).not.toHaveProperty('dota_lobby_password');
  });

  it('sends the start time converted to UTC', async () => {
    renderButton({ type: 'event', eventId: 42 });
    await openDialog();
    await screen.findByTestId('discord-message-preview');
    expect(mocks.preview.mock.calls[0][0].values.scheduled_at).toBe(
      '2026-12-04T18:00:00.000Z',
    );
  });

  it('fetches no roles or channels before the dialog opens', async () => {
    renderButton({ type: 'event', eventId: 42 });
    expect(mocks.roles).not.toHaveBeenCalled();
    expect(mocks.channels).not.toHaveBeenCalled();
    expect(mocks.preview).not.toHaveBeenCalled();
    await openDialog();
    await screen.findByTestId('discord-message-preview');
    expect(mocks.roles).toHaveBeenCalledWith(7);
  });

  it('titles the dialog with the kind and shows destination with channel names', async () => {
    renderButton({ type: 'event', eventId: 42 });
    const dialog = await openDialog();
    expect(within(dialog).getByRole('heading')).toHaveTextContent(
      'Signup post',
    );
    expect(
      await within(dialog).findByText(
        'Posts in #event-signups as a new thread "Friday Inhouse".',
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText('If that fails, posts in #announcements.'),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText('Ready: this is sent at its scheduled time.'),
    ).toBeInTheDocument();
  });

  it('explains why nothing is sent and lists notes', async () => {
    mocks.preview.mockResolvedValue(
      previewResponse({
        gate: { would_send: false, reasons: ['toggle_off', 'no_channel'] },
        notes: ['edits_refresh_embed_only'],
      }),
    );
    renderButton({ type: 'event', eventId: 42 });
    const dialog = await openDialog();
    expect(
      await within(dialog).findByText(
        'Off: nothing is sent until you turn this on',
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText('Not sent: no channel is selected.'),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Later signup changes update this post's embed and buttons only.",
      ),
    ).toBeInTheDocument();
  });

  it('shows the unsaved banner when the preview is not from a saved event', async () => {
    mocks.preview.mockResolvedValue(previewResponse({ saved: false }));
    renderButton({ type: 'new_event', organizationId: 7 });
    const dialog = await openDialog();
    expect(
      await within(dialog).findByTestId('discord-preview-unsaved'),
    ).toBeInTheDocument();
  });

  it('lists missing fields when the form cannot be previewed yet', async () => {
    mocks.preview.mockResolvedValue(
      previewResponse({
        status: 'needs_input',
        missing: ['name', 'scheduled_at'],
        messages: [],
        destination: null,
      }),
    );
    renderButton({ type: 'new_event', organizationId: 7 });
    const dialog = await openDialog();
    expect(
      await within(dialog).findByText(
        'Fill in these fields to see a preview: Name, Date and time',
      ),
    ).toBeInTheDocument();
  });

  it('renders the scheduled event card', async () => {
    mocks.preview.mockResolvedValue(
      previewResponse({
        kind: 'scheduled_event',
        destination: {
          type: 'scheduled_event',
          channel_id: null,
          thread_name: null,
          fallback_channel_id: null,
          reply_to_message_id: null,
        },
        messages: [],
        scheduled_event: {
          name: 'Friday Inhouse',
          description: 'Snacks &amp; drinks',
          scheduled_start_time: '2026-12-04T23:00:00Z',
          scheduled_end_time: null,
          entity_metadata: { location: 'DraftForge' },
        },
      }),
    );
    renderButton({ type: 'event', eventId: 42 }, 'scheduled_event');
    const dialog = await openDialog('scheduled_event');
    const card = await within(dialog).findByTestId('discord-scheduled-event');
    expect(card).toHaveTextContent('Friday Inhouse');
    expect(card).toHaveTextContent('Snacks &amp; drinks');
  });

  it('shows the start-mention header when no one would be mentioned', async () => {
    mocks.preview.mockResolvedValue(
      previewResponse({
        kind: 'start_mention',
        gate: { would_send: false, reasons: ['no_recipients'] },
        messages: [],
        note_args: { header: 'Friday Inhouse starts soon!' },
      }),
    );
    renderButton({ type: 'event', eventId: 42 }, 'start_mention');
    const dialog = await openDialog('start_mention');
    const box = await within(dialog).findByTestId(
      'discord-preview-start-mention-header',
    );
    expect(box).toHaveTextContent('Friday Inhouse starts soon!');
    expect(
      within(dialog).getByText(
        'No one would be mentioned right now; nothing is sent.',
      ),
    ).toBeInTheDocument();
  });

  it('shows the message of a 400 in the dialog', async () => {
    mocks.preview.mockRejectedValue({
      response: {
        status: 400,
        data: { max_players: ['A valid integer is required.'] },
      },
    });
    renderButton({ type: 'event', eventId: 42 });
    const dialog = await openDialog();
    expect(
      await within(dialog).findByText('A valid integer is required.'),
    ).toBeInTheDocument();
  });

  it('shows a static body and makes no request without a context', async () => {
    renderButton(undefined);
    const dialog = await openDialog();
    expect(
      within(dialog).getByTestId('discord-preview-unavailable'),
    ).toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.roles).not.toHaveBeenCalled();
  });
});
