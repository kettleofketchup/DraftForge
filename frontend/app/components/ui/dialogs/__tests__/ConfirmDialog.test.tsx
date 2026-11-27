// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Input } from '~/components/ui/input';
import { TooltipProvider } from '~/components/ui/tooltip';
import { ConfirmDialog } from '../ConfirmDialog';
import { DeleteDialog } from '../DeleteDialog';

// NOTE: This file uses @testing-library/react instead of the project's
// usual react-dom/server + renderToStaticMarkup convention (see
// useUserDotaProfile.test.tsx). ConfirmDialog is a stateful Radix
// portal with no extractable pure helpers, so we need real DOM rendering
// to assert on the portal's children. Future component tests for portal
// dialogs can follow this pattern; pure helper tests should continue to
// use renderToStaticMarkup or no DOM at all.

// CancelButton/ConfirmButton render HotkeyBadge with LazyTooltip which
// requires a TooltipProvider ancestor.
function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

describe('ConfirmDialog additive props', () => {
  it('forwards contentTestId, titleTestId, descriptionTestId to the right elements', () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Test title"
        description="Test description"
        onConfirm={() => {}}
        contentTestId="my-content"
        titleTestId="my-title"
        descriptionTestId="my-desc"
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('my-content')).toBeInTheDocument();
    expect(screen.getByTestId('my-title')).toHaveTextContent('Test title');
    expect(screen.getByTestId('my-desc')).toHaveTextContent('Test description');
  });

  it('renders bodyContent as a sibling between header and footer when provided', () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="t"
        description="d"
        onConfirm={() => {}}
        bodyContent={<div data-testid="my-body">extra content</div>}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('my-body')).toHaveTextContent('extra content');
  });

  it('does NOT render any extra wrapper when bodyContent is omitted', () => {
    const { container } = render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="t"
        description="d"
        onConfirm={() => {}}
      />,
      { wrapper: Wrapper },
    );
    expect(
      container.querySelector('[data-testid="confirm-dialog-body-slot"]'),
    ).toBeNull();
  });

  it('disables the confirm button when confirmDisabled is true', () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="t"
        description="d"
        onConfirm={() => {}}
        confirmDisabled
        confirmTestId="cd-confirm"
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('cd-confirm')).toBeDisabled();
  });
});

describe('ConfirmDialog keyboard activation', () => {
  it.each(['Cancel', 'Keep'])(
    'Enter activates focused %s without confirming',
    async (cancelLabel) => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      const onOpenChange = vi.fn();
      render(
        <ConfirmDialog
          open
          title="Confirm?"
          description="Details"
          onConfirm={onConfirm}
          onOpenChange={onOpenChange}
          cancelLabel={cancelLabel}
          cancelTestId="cancel"
          confirmTestId="confirm"
          contentTestId="content"
        />,
        { wrapper: Wrapper },
      );
      screen.getByTestId('cancel').focus();
      expect(screen.getByTestId('cancel')).toHaveFocus();
      await user.keyboard('{Enter}');
      expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
      expect(onConfirm).not.toHaveBeenCalled();
    },
  );

  it('Enter activates focused Confirm exactly once', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Confirm?"
        description="Details"
        onConfirm={onConfirm}
        onOpenChange={() => {}}
        confirmTestId="confirm"
      />,
      { wrapper: Wrapper },
    );
    screen.getByTestId('confirm').focus();
    await user.keyboard('{Enter}');
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it.each([false, true])(
    'content shortcuts respect confirmDisabled=%s',
    async (confirmDisabled) => {
      const user = userEvent.setup();
      const onConfirm = vi.fn();
      const onOpenChange = vi.fn();
      render(
        <ConfirmDialog
          open
          title="Confirm?"
          description="Details"
          onConfirm={onConfirm}
          onOpenChange={onOpenChange}
          confirmDisabled={confirmDisabled}
          contentTestId="content"
        />,
        { wrapper: Wrapper },
      );
      screen.getByTestId('content').focus();
      await user.keyboard('{Enter}');
      expect(onConfirm).toHaveBeenCalledTimes(confirmDisabled ? 0 : 1);
      onOpenChange.mockClear();
      await user.keyboard('{Backspace}');
      expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
    },
  );

  it('does not intercept typing inside an input', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Confirm?"
        description="Details"
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
        bodyContent={<Input data-testid="input" />}
      />,
      { wrapper: Wrapper },
    );
    await user.click(screen.getByTestId('input'));
    await user.keyboard('x{Enter}{Backspace}');
    expect(screen.getByTestId('input')).toHaveValue('');
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('ignores shortcuts while submitting', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open
        isLoading
        title="Confirm?"
        description="Details"
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
        contentTestId="content"
        cancelTestId="cancel"
        confirmTestId="confirm"
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('cancel')).toBeDisabled();
    expect(screen.getByTestId('confirm')).toBeDisabled();
    screen.getByTestId('content').focus();
    await user.keyboard('{Enter}{Backspace}');
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('Cancel in DeleteDialog stays safe after its typed confirmation matches', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <DeleteDialog
        open
        entityKind="Event"
        entityName="Example"
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
        inputTestId="input"
        cancelTestId="cancel"
        confirmTestId="confirm"
      />,
      { wrapper: Wrapper },
    );
    await user.type(screen.getByTestId('input'), 'Example');
    expect(screen.getByTestId('confirm')).toBeEnabled();
    screen.getByTestId('cancel').focus();
    expect(screen.getByTestId('cancel')).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe('ConfirmDialog surface', () => {
  const translucentBg = /(^|\s)bg-[a-z-]+(-\d+)?\/\d+/;

  it.each([
    [
      'default',
      'bg-success-surface',
      '[background-image:var(--brand-success-bg)]',
    ],
    [
      'destructive',
      'bg-background',
      '[background-image:var(--brand-destructive-bg)]',
    ],
    ['warning', 'bg-background', '[background-image:var(--brand-warning-bg)]'],
  ] as const)(
    '%s variant sits on an opaque background',
    (variant, base, tint) => {
      render(
        <ConfirmDialog
          open
          onOpenChange={() => {}}
          title="t"
          description="d"
          onConfirm={() => {}}
          variant={variant}
          contentTestId="surface"
        />,
        { wrapper: Wrapper },
      );
      const className = screen.getByTestId('surface').className;
      expect(className).not.toMatch(translucentBg);
      expect(className.split(/\s+/)).toContain(base);
      expect(className.split(/\s+/)).toContain(tint);
    },
  );
});
