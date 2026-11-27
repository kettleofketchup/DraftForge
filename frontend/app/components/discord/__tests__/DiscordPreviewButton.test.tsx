// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';
import { createI18nInstance } from '~/i18n/config';
import { DiscordPreviewButton } from '../DiscordPreviewButton';

function wrap(ui: ReactNode, i18n = createI18nInstance('en')) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </I18nextProvider>,
  );
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const renderText = (data: string) => <p data-testid="payload">{data}</p>;

function openButton(name: RegExp | string = /preview signup post/i) {
  fireEvent.click(screen.getByRole('button', { name }));
}

function closeDialog() {
  const dialog = screen.getByTestId('discord-preview-dialog');
  fireEvent.click(within(dialog).getAllByRole('button', { name: 'Close' })[0]);
}

describe('DiscordPreviewButton: button', () => {
  it('uses i18n defaults for label and accessible name', () => {
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        fetchPreview={vi.fn()}
        render={renderText}
        data-testid="discord-preview-signup_post"
      />,
    );
    const button = screen.getByTestId('discord-preview-signup_post');
    expect(button).toHaveTextContent('Preview');
    expect(button).toHaveAccessibleName('Preview Signup post');
    expect(button).toHaveAttribute('type', 'button');
  });

  it('accepts label and ariaLabel overrides', () => {
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        label="Look"
        ariaLabel="Look at it"
        fetchPreview={vi.fn()}
        render={renderText}
      />,
    );
    const button = screen.getByRole('button', { name: 'Look at it' });
    expect(button).toHaveTextContent('Look');
  });

  it('is disabled with a reason shown as a tooltip and does not fetch', async () => {
    const fetchPreview = vi.fn();
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        fetchPreview={fetchPreview}
        render={renderText}
        disabled
        disabledReason="Pick a channel first"
      />,
    );
    const button = screen.getByRole('button', { name: /preview signup post/i });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(screen.queryByTestId('discord-preview-dialog')).toBeNull();
    fireEvent.focus(screen.getByTestId('discord-preview-disabled-trigger'));
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Pick a channel first',
    );
    expect(fetchPreview).not.toHaveBeenCalled();
  });
});

describe('DiscordPreviewButton: dialog', () => {
  it('titles the dialog and translates close and description', async () => {
    const i18n = createI18nInstance('en');
    i18n.addResourceBundle(
      'en',
      'discordPreview',
      {
        dialog: {
          close: 'CLOSE_SENTINEL',
          description: 'DESC_SENTINEL',
        },
      },
      true,
      true,
    );
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        body={<p>static</p>}
      />,
      i18n,
    );
    openButton();
    const dialog = await screen.findByTestId('discord-preview-dialog');
    expect(
      within(dialog).getByRole('heading', { name: 'Signup post' }),
    ).toBeInTheDocument();
    expect(within(dialog).getByText('DESC_SENTINEL')).toBeInTheDocument();
    expect(
      within(dialog).getByRole('button', { name: 'CLOSE_SENTINEL' }),
    ).toHaveTextContent('CLOSE_SENTINEL');
    expect(within(dialog).queryByText('Signup post dialog')).toBeNull();
  });

  it('uses a caller description when given', async () => {
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        description="Custom description"
        body={<p>static</p>}
      />,
    );
    openButton();
    expect(await screen.findByText('Custom description')).toBeInTheDocument();
  });

  it('renders the static body without fetching when no fetcher is given', async () => {
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        body={<p>Available when editing an event</p>}
      />,
    );
    openButton();
    expect(
      await screen.findByText('Available when editing an event'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('discord-preview-loading')).toBeNull();
  });
});

describe('DiscordPreviewButton: fetching', () => {
  it('does not fetch before opening', () => {
    const fetchPreview = vi.fn().mockResolvedValue('A');
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        fetchPreview={fetchPreview}
        render={renderText}
      />,
    );
    expect(fetchPreview).not.toHaveBeenCalled();
  });

  it('shows a skeleton while loading, then the payload', async () => {
    const d = deferred<string>();
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        fetchPreview={() => d.promise}
        render={renderText}
      />,
    );
    openButton();
    expect(
      await screen.findByTestId('discord-preview-loading'),
    ).toBeInTheDocument();
    await act(async () => d.resolve('A'));
    expect(await screen.findByTestId('payload')).toHaveTextContent('A');
    expect(screen.queryByTestId('discord-preview-loading')).toBeNull();
  });

  it('fetches once per open and again on reopen', async () => {
    const fetchPreview = vi
      .fn()
      .mockResolvedValueOnce('first')
      .mockResolvedValueOnce('second');
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        fetchPreview={fetchPreview}
        render={renderText}
      />,
    );
    openButton();
    expect(await screen.findByTestId('payload')).toHaveTextContent('first');
    expect(fetchPreview).toHaveBeenCalledTimes(1);
    closeDialog();
    await waitFor(() =>
      expect(screen.queryByTestId('discord-preview-dialog')).toBeNull(),
    );
    openButton();
    expect(await screen.findByTestId('payload')).toHaveTextContent('second');
    expect(fetchPreview).toHaveBeenCalledTimes(2);
  });

  it('shows the second payload when closed while pending and reopened', async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const fetchPreview = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        fetchPreview={fetchPreview}
        render={renderText}
      />,
    );
    openButton();
    await screen.findByTestId('discord-preview-loading');
    closeDialog();
    await waitFor(() =>
      expect(screen.queryByTestId('discord-preview-dialog')).toBeNull(),
    );
    openButton();
    await screen.findByTestId('discord-preview-loading');
    await act(async () => first.resolve('A'));
    expect(screen.queryByTestId('payload')).toBeNull();
    await act(async () => second.resolve('B'));
    expect(await screen.findByTestId('payload')).toHaveTextContent('B');
    expect(screen.queryByText('A')).toBeNull();
    expect(fetchPreview).toHaveBeenCalledTimes(2);
  });

  it('shows the API error message and Retry refetches', async () => {
    const fetchPreview = vi
      .fn()
      .mockRejectedValueOnce({
        response: { data: { error: 'Invalid preview request.' } },
      })
      .mockResolvedValueOnce('ok');
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        fetchPreview={fetchPreview}
        render={renderText}
      />,
    );
    openButton();
    expect(
      await screen.findByText('Invalid preview request.'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByTestId('payload')).toHaveTextContent('ok');
    expect(fetchPreview).toHaveBeenCalledTimes(2);
  });

  it('falls back to a generic error message', async () => {
    const fetchPreview = vi.fn().mockRejectedValue(new Error('boom'));
    wrap(
      <DiscordPreviewButton
        queryKey={['k']}
        title="Signup post"
        fetchPreview={fetchPreview}
        render={renderText}
      />,
    );
    openButton();
    expect(
      await screen.findByText('Could not load the preview.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('keeps payloads apart for two buttons with different keys', async () => {
    wrap(
      <>
        <DiscordPreviewButton
          queryKey={['preview', 'a']}
          title="Alpha"
          fetchPreview={() => Promise.resolve('alpha payload')}
          render={renderText}
        />
        <DiscordPreviewButton
          queryKey={['preview', 'b']}
          title="Beta"
          fetchPreview={() => Promise.resolve('beta payload')}
          render={renderText}
        />
      </>,
    );
    openButton('Preview Alpha');
    expect(await screen.findByTestId('payload')).toHaveTextContent(
      'alpha payload',
    );
    closeDialog();
    await waitFor(() =>
      expect(screen.queryByTestId('discord-preview-dialog')).toBeNull(),
    );
    openButton('Preview Beta');
    expect(await screen.findByTestId('payload')).toHaveTextContent(
      'beta payload',
    );
  });
});

describe('DiscordPreviewButton: inside a form', () => {
  it('opens the dialog without submitting the form', async () => {
    const onSubmit = vi.fn((e: { preventDefault: () => void }) =>
      e.preventDefault(),
    );
    wrap(
      <form onSubmit={onSubmit}>
        <DiscordPreviewButton
          queryKey={['k']}
          title="Signup post"
          fetchPreview={() => Promise.resolve('A')}
          render={renderText}
        />
      </form>,
    );
    openButton();
    expect(await screen.findByTestId('payload')).toHaveTextContent('A');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('stays type=button even when the caller passes type=submit', async () => {
    const onSubmit = vi.fn((e: { preventDefault: () => void }) =>
      e.preventDefault(),
    );
    const props = { type: 'submit' } as unknown as Record<string, never>;
    wrap(
      <form onSubmit={onSubmit}>
        <DiscordPreviewButton
          queryKey={['k']}
          title="Signup post"
          fetchPreview={() => Promise.reject(new Error('x'))}
          render={renderText}
          {...props}
        />
      </form>,
    );
    const button = screen.getByRole('button', { name: /preview signup post/i });
    expect(button).toHaveAttribute('type', 'button');
    fireEvent.click(button);
    const retry = await screen.findByRole('button', { name: 'Retry' });
    expect(retry).toHaveAttribute('type', 'button');
    fireEvent.click(retry);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
