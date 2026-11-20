// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { TeamActionReasonDialog } from '../TeamActionReasonDialog';
import { people } from './fixtures';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

type Props = Parameters<typeof TeamActionReasonDialog>[0];

function renderDialog(overrides: Partial<Props> = {}) {
  const onSubmit = vi.fn<Props['onSubmit']>(() => Promise.resolve());
  const onOpenChange = vi.fn();
  render(
    <TooltipProvider>
      <TeamActionReasonDialog
        open
        onOpenChange={onOpenChange}
        title="Change captain?"
        summary="Make Bar captain of Team X"
        confirmText="Make captain"
        pending={false}
        onSubmit={onSubmit}
        {...overrides}
      />
    </TooltipProvider>,
  );
  return { onSubmit, onOpenChange };
}

function typeReason(value: string) {
  fireEvent.change(screen.getByTestId('team-action-reason'), {
    target: { value },
  });
}

describe('TeamActionReasonDialog', () => {
  it('renders the summary, warning and confirm text', () => {
    renderDialog({ warning: 'Ready state resets' });
    expect(screen.getByText('Make Bar captain of Team X')).toBeTruthy();
    expect(screen.getByText('Ready state resets')).toBeTruthy();
    expect(screen.getByTestId('team-action-confirm').textContent).toContain(
      'Make captain',
    );
  });

  it('enables confirm only once the reason has 3 characters', async () => {
    renderDialog();
    const confirm = screen.getByTestId('team-action-confirm');
    typeReason('ab');
    await waitFor(() => expect(confirm).toHaveProperty('disabled', true));
    typeReason('abc');
    await waitFor(() => expect(confirm).toHaveProperty('disabled', false));
  });

  it('submits the trimmed reason', async () => {
    const { onSubmit } = renderDialog();
    typeReason('  left the team  ');
    const confirm = screen.getByTestId('team-action-confirm');
    await waitFor(() => expect(confirm).toHaveProperty('disabled', false));
    fireEvent.click(confirm);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toEqual({ reason: 'left the team' });
  });

  it('prefills defaultReason', async () => {
    renderDialog({ defaultReason: 'previous reason' });
    expect(
      (screen.getByTestId('team-action-reason') as HTMLTextAreaElement).value,
    ).toBe('previous reason');
    await waitFor(() =>
      expect(screen.getByTestId('team-action-confirm')).toHaveProperty(
        'disabled',
        false,
      ),
    );
  });

  it('does not submit while pending', async () => {
    const { onSubmit } = renderDialog({
      pending: true,
      defaultReason: 'valid reason',
    });
    fireEvent.click(screen.getByTestId('team-action-confirm'));
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Enter' });
    await new Promise((r) => setTimeout(r, 20));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('calls onSubmit once for two synchronous clicks', async () => {
    let resolve: () => void = () => undefined;
    const onSubmit = vi.fn<Props['onSubmit']>(
      () =>
        new Promise<void>((r) => {
          resolve = r;
        }),
    );
    const { onOpenChange } = renderDialog({
      onSubmit,
      defaultReason: 'valid reason',
    });
    const confirm = screen.getByTestId('team-action-confirm');
    await waitFor(() => expect(confirm).toHaveProperty('disabled', false));
    act(() => {
      fireEvent.click(confirm);
      fireEvent.click(confirm);
    });
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    fireEvent.click(confirm);
    await new Promise((r) => setTimeout(r, 20));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onOpenChange).not.toHaveBeenCalled();
    await act(async () => {
      resolve();
    });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  describe('replacing select', () => {
    const options = [people.member, people.deputy];

    function openReplacing(): HTMLElement {
      fireEvent.pointerDown(screen.getByTestId('team-action-replacing'), {
        button: 0,
        ctrlKey: false,
        pointerType: 'mouse',
      });
      return screen.getByRole('listbox');
    }

    async function confirm() {
      const button = screen.getByTestId('team-action-confirm');
      await waitFor(() => expect(button).toHaveProperty('disabled', false));
      fireEvent.click(button);
    }

    it('explains what replacing does', () => {
      renderDialog({ replacingOptions: options });
      expect(
        screen.getByText(
          'Without a replacement the stand-in joins the roster. With one, the replaced player becomes a dropout.',
        ),
      ).toBeTruthy();
    });

    it('sends replacing_id null for "No one"', async () => {
      const { onSubmit } = renderDialog({
        replacingOptions: options,
        defaultReason: 'cover for tonight',
      });
      await confirm();
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0]).toEqual({
        reason: 'cover for tonight',
        replacing_id: null,
      });
    });

    it('warns only when the captain is being replaced', () => {
      renderDialog({
        replacingOptions: [people.captain, people.member],
        replacingCaptain: { pk: people.captain.pk, warning: 'Draft resets' },
      });
      expect(screen.queryByText('Draft resets')).toBeNull();
      let listbox = openReplacing();
      const captainOption = within(listbox).getByRole('option', {
        name: `${DisplayName(people.captain)} (captain)`,
      });
      fireEvent.click(captainOption);
      expect(screen.getByTestId('team-action-warning')).toHaveTextContent(
        'Draft resets',
      );
      listbox = openReplacing();
      fireEvent.click(
        within(listbox).getByRole('option', {
          name: DisplayName(people.member),
        }),
      );
      expect(screen.queryByText('Draft resets')).toBeNull();
    });

    it('sends the chosen player pk', async () => {
      const { onSubmit } = renderDialog({
        replacingOptions: options,
        defaultReason: 'cover for tonight',
      });
      const listbox = openReplacing();
      fireEvent.click(
        within(listbox).getByRole('option', {
          name: DisplayName(people.member),
        }),
      );
      await confirm();
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0]).toEqual({
        reason: 'cover for tonight',
        replacing_id: people.member.pk,
      });
    });
  });
});
