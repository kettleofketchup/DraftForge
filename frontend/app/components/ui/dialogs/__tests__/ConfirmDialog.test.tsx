// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { TooltipProvider } from '~/components/ui/tooltip';
import { ConfirmDialog } from '../ConfirmDialog';

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
    expect(container.querySelector('[data-testid="confirm-dialog-body-slot"]')).toBeNull();
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
