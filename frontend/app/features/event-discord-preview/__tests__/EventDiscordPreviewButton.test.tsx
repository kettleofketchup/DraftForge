// @vitest-environment jsdom
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { useForm } from 'react-hook-form';
import { I18nextProvider, setI18n } from 'react-i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  eventFieldTestIds,
  EventFormDialog,
  EventIdentityFields,
  OneOffScheduleFields,
} from '~/components/events/form';
import {
  EventFormNavigationProvider,
  type EventFormNavigation,
} from '~/components/events/form/EventFormNavigation';
import { Form } from '~/components/ui/form';
import { TooltipProvider } from '~/components/ui/tooltip';
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

function renderWithNavigation(
  context: DiscordPreviewContext,
  kind: Parameters<typeof EventDiscordPreviewButton>[0]['kind'],
) {
  const navigation: EventFormNavigation = { navigateToField: vi.fn() };
  const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
  render(
    <TestQueryClientProvider>
      <FormHarness values={{ name: '', timezone: 'UTC' }}>
        <EventFormNavigationProvider value={navigation}>
          <form onSubmit={onSubmit}>
            <EventDiscordPreviewButton
              kind={kind}
              organizationId={7}
              context={context}
            />
          </form>
        </EventFormNavigationProvider>
      </FormHarness>
    </TestQueryClientProvider>,
  );
  return { navigateToField: navigation.navigateToField, onSubmit };
}

function needsInput(missing: string[]) {
  mocks.preview.mockResolvedValue(
    previewResponse({
      status: 'needs_input',
      missing,
      messages: [],
      destination: null,
    }),
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

  describe('missing prerequisite actions', () => {
    it('maps schedule to frequency after closing the preview', async () => {
      needsInput(['schedule']);
      const { navigateToField, onSubmit } = renderWithNavigation(
        { type: 'repeater', repeaterId: 3 },
        'scheduled_event',
      );
      const dialog = await openDialog('scheduled_event');
      const action = await within(dialog).findByTestId(
        'discord-preview-missing-schedule',
      );
      expect(action).toHaveAttribute('type', 'button');
      expect(action).toHaveTextContent('Schedule');
      expect(
        within(dialog).getByText('Fill in these fields to see a preview:'),
      ).toBeInTheDocument();
      fireEvent.click(action);
      await waitFor(() =>
        expect(navigateToField).toHaveBeenCalledWith('frequency'),
      );
      expect(navigateToField).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId('discord-preview-dialog')).toBeNull();
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it.each([
      ['name', 'name'],
      ['scheduled_at', 'scheduled_at'],
    ])('exposes a separate %s action', async (code, field) => {
      needsInput(['name', 'scheduled_at']);
      const { navigateToField, onSubmit } = renderWithNavigation(
        { type: 'new_event', organizationId: 7 },
        'signup_post',
      );
      const dialog = await openDialog();
      await within(dialog).findByTestId('discord-preview-missing-name');
      expect(
        within(dialog).getByTestId('discord-preview-missing-scheduled_at'),
      ).toHaveTextContent('Date and time');
      fireEvent.click(
        within(dialog).getByTestId(`discord-preview-missing-${code}`),
      );
      await waitFor(() => expect(navigateToField).toHaveBeenCalledTimes(1));
      expect(navigateToField).toHaveBeenCalledWith(field);
      expect(screen.queryByTestId('discord-preview-dialog')).toBeNull();
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it.each([
      ['name', 'one-off-name-input'],
      ['scheduled_at', 'one-off-scheduled-input'],
    ])(
      'reveals %s in a one-off host and keeps the unsaved description',
      async (code, testId) => {
        needsInput(['name', 'scheduled_at']);
        const onValid = vi.fn();
        const ids = eventFieldTestIds('one-off');
        function OneOffHost() {
          const form = useForm<{
            name: string;
            description: string;
            scheduled_at: string;
          }>({
            defaultValues: { name: '', description: '', scheduled_at: '' },
          });
          return (
            <EventFormDialog
              open
              onOpenChange={() => {}}
              title="Add one-off event"
              submitLabel="Create"
              form={form}
              onValid={onValid}
              isSubmitting={false}
              tabTestIdPrefix="one-off"
              tabs={[
                {
                  value: 'event',
                  content: (
                    <>
                      <EventIdentityFields
                        control={form.control}
                        testIds={ids}
                      />
                      <OneOffScheduleFields
                        control={form.control}
                        testIds={ids}
                        showEndsAt={false}
                      />
                    </>
                  ),
                },
                {
                  value: 'discord',
                  lazy: true,
                  content: (
                    <EventDiscordPreviewButton
                      kind="signup_post"
                      organizationId={7}
                      context={{ type: 'series_one_off', repeaterId: 3 }}
                    />
                  ),
                },
              ]}
            />
          );
        }
        render(
          <TestQueryClientProvider>
            <TooltipProvider>
              <OneOffHost />
            </TooltipProvider>
          </TestQueryClientProvider>,
        );
        fireEvent.change(screen.getByTestId('one-off-description-input'), {
          target: { value: 'Unsaved description' },
        });
        fireEvent.mouseDown(screen.getByTestId('one-off-tab-discord'), {
          button: 0,
        });
        const dialog = await openDialog();
        fireEvent.click(
          await within(dialog).findByTestId(`discord-preview-missing-${code}`),
        );
        await waitFor(() => expect(screen.getByTestId(testId)).toHaveFocus());
        expect(screen.queryByTestId('discord-preview-dialog')).toBeNull();
        expect(screen.getByTestId('one-off-tab-event')).toHaveAttribute(
          'aria-selected',
          'true',
        );
        expect(screen.getByTestId('one-off-description-input')).toHaveValue(
          'Unsaved description',
        );
        expect(onValid).not.toHaveBeenCalled();
      },
    );

    it.each(['<img onerror=x>[data-field=x]', '__proto__', 'constructor'])(
      'leaves unknown prerequisite %s as escaped text',
      async (unknown) => {
        needsInput(['name', 'scheduled_at', unknown]);
        const { navigateToField } = renderWithNavigation(
          { type: 'new_event', organizationId: 7 },
          'signup_post',
        );
        const dialog = await openDialog();
        const list = await within(dialog).findByTestId(
          'discord-preview-needs-input',
        );
        expect(within(list).getByText(unknown).tagName).toBe('LI');
        expect(list.querySelector('img')).toBeNull();
        expect(within(list).getAllByRole('button')).toHaveLength(2);
        expect(
          list.querySelector('[data-testid^="discord-preview-missing-<"]'),
        ).toBeNull();
        expect(navigateToField).not.toHaveBeenCalled();
      },
    );

    it('falls back to text without a navigation provider', async () => {
      needsInput(['schedule']);
      renderButton({ type: 'repeater', repeaterId: 3 }, 'scheduled_event');
      const dialog = await openDialog('scheduled_event');
      expect(
        await within(dialog).findByText(
          'Fill in these fields to see a preview: Schedule',
        ),
      ).toBeInTheDocument();
      expect(
        within(dialog).queryByTestId('discord-preview-missing-schedule'),
      ).toBeNull();
    });

    it('stays static and makes no request for defaults with a provider', async () => {
      const navigation: EventFormNavigation = { navigateToField: vi.fn() };
      render(
        <TestQueryClientProvider>
          <FormHarness values={{}}>
            <EventFormNavigationProvider value={navigation}>
              <EventDiscordPreviewButton
                kind="scheduled_event"
                organizationId={7}
              />
            </EventFormNavigationProvider>
          </FormHarness>
        </TestQueryClientProvider>,
      );
      const dialog = await openDialog('scheduled_event');
      expect(
        within(dialog).getByTestId('discord-preview-unavailable'),
      ).toBeInTheDocument();
      expect(mocks.preview).not.toHaveBeenCalled();
    });

    it('renders translated prerequisite actions in Spanish', async () => {
      setI18n(createI18nInstance('es'));
      needsInput(['name', 'scheduled_at', 'schedule']);
      renderWithNavigation(
        { type: 'repeater', repeaterId: 3 },
        'scheduled_event',
      );
      const dialog = await openDialog('scheduled_event');
      expect(
        await within(dialog).findByText(
          'Completa estos campos para ver una vista previa:',
        ),
      ).toBeInTheDocument();
      expect(
        within(dialog).getByTestId('discord-preview-missing-name'),
      ).toHaveTextContent('Nombre');
      expect(
        within(dialog).getByTestId('discord-preview-missing-scheduled_at'),
      ).toHaveTextContent('Fecha y hora');
      expect(
        within(dialog).getByTestId('discord-preview-missing-schedule'),
      ).toHaveTextContent('Horario');
    });
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
