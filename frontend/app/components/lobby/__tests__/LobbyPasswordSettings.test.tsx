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
  })
  .superRefine(refineLobbyPassword);

type Values = z.infer<typeof schema>;

function Harness({
  values,
  scope = 'event',
  saved,
  onRegenerate,
  onSubmit = () => {},
}: {
  values: Values;
  scope?: 'series' | 'event';
  saved?: LobbyPasswordInfo | null;
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
        onRegenerate={onRegenerate}
      />,
    );
    expect(screen.getByTestId('lobby-password-current')).toHaveTextContent('abcd2345wxyz');
    expect(screen.getByTestId('lobby-password-copy')).toBeInTheDocument();
    expect(screen.getByTestId('lobby-password-from-series')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('lobby-password-regenerate'));
    await waitFor(() => expect(onRegenerate).toHaveBeenCalledOnce());
  });

  it('random series: explains that each event gets its own', () => {
    render(
      <Harness values={{ dota_lobby_password_mode: 'random', dota_lobby_password: '' }} scope="series" />,
    );
    expect(screen.queryByTestId('lobby-password-input')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-password-regenerate')).not.toBeInTheDocument();
    expect(screen.getByText(/its own generated password/)).toBeInTheDocument();
    expect(screen.getByText(/anyone who has it can join any of them/)).toBeInTheDocument();
  });
});
