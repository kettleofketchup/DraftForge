// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { I18nextProvider } from 'react-i18next';
import { z } from 'zod';
import { Form } from '~/components/ui/form';
import { createI18nInstance } from '~/i18n/config';
import { LobbyPasswordSettings } from '../LobbyPasswordSettings';
import { refineLobbyPassword } from '../password';
import type { LobbyPasswordInfo } from '../schemas';

const schema = z
  .object({
    dota_lobby_password_mode: z.enum(['random', 'fixed']),
    dota_lobby_password: z.string(),
    dota_lobby_password_saved: z.boolean().optional(),
  })
  .superRefine(refineLobbyPassword);

type Values = z.infer<typeof schema>;

function Harness({
  values,
  scope = 'event',
  saved,
  followsSeries,
  onRegenerate,
  onSubmit = () => {},
}: {
  values: Values;
  scope?: 'series' | 'event';
  saved?: LobbyPasswordInfo | null;
  followsSeries?: boolean;
  onRegenerate?: () => void;
  onSubmit?: (v: Values) => void;
}) {
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: values });
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)}>
          <LobbyPasswordSettings
            control={form.control}
            watch={form.watch}
            scope={scope}
            saved={saved}
            followsSeries={followsSeries}
            onRegenerate={onRegenerate}
          />
          <button type="submit">save</button>
        </form>
      </Form>
    </I18nextProvider>
  );
}

afterEach(cleanup);

describe('LobbyPasswordSettings', () => {
  it('fixed mode: hidden input with a show/hide toggle', () => {
    render(<Harness values={{ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'pw' }} />);
    const input = screen.getByTestId('lobby-password-input');
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('maxLength', '32');
    fireEvent.click(screen.getByTestId('lobby-password-toggle'));
    expect(input).toHaveAttribute('type', 'text');
    expect(screen.queryByTestId('lobby-password-regenerate')).not.toBeInTheDocument();
  });

  it('shows a translated error for an invalid fixed password', async () => {
    const onSubmit = vi.fn();
    render(
      <Harness
        values={{ dota_lobby_password_mode: 'fixed', dota_lobby_password: ' padded' }}
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(screen.getByText('save'));
    expect(await screen.findByTestId('lobby-password-error')).toHaveTextContent(
      'cannot start or end with a space',
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('random event: current password, copy and regenerate', async () => {
    const onRegenerate = vi.fn();
    render(
      <Harness
        values={{ dota_lobby_password_mode: 'random', dota_lobby_password: '' }}
        saved={{ mode: 'random', password: 'abcd2345wxyz', source: 'series', can_manage: true }}
        followsSeries
        onRegenerate={onRegenerate}
      />,
    );
    expect(screen.getByTestId('lobby-password-leak-help')).toHaveTextContent(/regenerate it/);
    expect(screen.getByTestId('lobby-password-current')).toHaveTextContent('abcd2345wxyz');
    expect(screen.getByTestId('lobby-password-copy')).toBeInTheDocument();
    expect(screen.getByTestId('lobby-password-from-series')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('lobby-password-regenerate'));
    await waitFor(() => expect(onRegenerate).toHaveBeenCalledOnce());
  });

  it('warns an event that overrides its series that a series save replaces it', () => {
    render(
      <Harness
        values={{ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'night4' }}
        saved={{ mode: 'fixed', password: 'night4', source: 'event', can_manage: true }}
        followsSeries
      />,
    );
    expect(screen.getByTestId('lobby-password-from-series')).toHaveTextContent(
      /overrides its series/,
    );
  });

  it('no series note for a standalone or off-schedule event', () => {
    render(
      <Harness
        values={{ dota_lobby_password_mode: 'random', dota_lobby_password: '' }}
        saved={{ mode: 'random', password: 'abcd2345wxyz', source: 'event', can_manage: true }}
      />,
    );
    expect(screen.queryByTestId('lobby-password-from-series')).not.toBeInTheDocument();
  });

  it('fixed mode: leak help says to set a new one, not to regenerate', () => {
    render(<Harness values={{ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'pw' }} />);
    const help = screen.getByTestId('lobby-password-leak-help');
    expect(help).toHaveTextContent(/set a new one/);
    expect(help).toHaveTextContent(/recreate/);
  });

  it('new random event: no leak help without a regenerate button', () => {
    render(<Harness values={{ dota_lobby_password_mode: 'random', dota_lobby_password: '' }} />);
    expect(screen.queryByTestId('lobby-password-leak-help')).not.toBeInTheDocument();
  });

  it('saved fixed password: an empty field keeps it', async () => {
    const onSubmit = vi.fn();
    render(
      <Harness
        values={{
          dota_lobby_password_mode: 'fixed',
          dota_lobby_password: '',
          dota_lobby_password_saved: true,
        }}
        onSubmit={onSubmit}
      />,
    );
    expect(screen.getByTestId('lobby-password-input')).toHaveAttribute(
      'placeholder',
      'Leave empty to keep the current password',
    );
    fireEvent.click(screen.getByText('save'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
  });

  it('random series: explains that each event gets its own', () => {
    render(
      <Harness values={{ dota_lobby_password_mode: 'random', dota_lobby_password: '' }} scope="series" />,
    );
    expect(screen.queryByTestId('lobby-password-input')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-password-regenerate')).not.toBeInTheDocument();
    expect(screen.getByText(/its own generated password/)).toBeInTheDocument();
    expect(screen.getByText(/anyone who has it can join any of them/)).toBeInTheDocument();
    expect(screen.getByTestId('lobby-password-leak-help')).toHaveTextContent(
      /in that event's settings/,
    );
  });
});
