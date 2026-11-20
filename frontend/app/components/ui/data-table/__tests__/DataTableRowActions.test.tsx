// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DataTableRowActions, type DataTableRowAction } from '..';
import { setViewportWidth } from './viewport';

afterEach(cleanup);

function openMenu(testId = 'row-actions-1'): void {
  fireEvent.pointerDown(screen.getByTestId(testId), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

function renderActions(
  actions: DataTableRowAction[],
  props: {
    disabled?: boolean;
    onRowClick?: () => void;
    inlineFrom?: 'md' | 'lg';
  } = {},
) {
  render(
    <div onClick={props.onRowClick}>
      <DataTableRowActions
        label="Actions for Alpha"
        actions={actions}
        disabled={props.disabled}
        inlineFrom={props.inlineFrom}
        data-testid="row-actions-1"
      />
    </div>,
  );
}

describe('DataTableRowActions', () => {
  it('labels the trigger and lists the actions as menu items', () => {
    renderActions([
      { key: 'edit', label: 'Edit', onSelect: vi.fn(), testId: 'edit-1' },
      {
        key: 'delete',
        label: 'Delete',
        onSelect: vi.fn(),
        destructive: true,
        testId: 'delete-1',
      },
    ]);
    expect(screen.getByTestId('row-actions-1')).toHaveAccessibleName(
      'Actions for Alpha',
    );
    openMenu();
    expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual([
      'Edit',
      'Delete',
    ]);
    expect(screen.getByTestId('delete-1')).toHaveClass('text-error');
  });

  it('runs the chosen action without reaching the row', () => {
    const onSelect = vi.fn();
    const onRowClick = vi.fn();
    renderActions([{ key: 'edit', label: 'Edit', onSelect }], { onRowClick });
    fireEvent.click(screen.getByTestId('row-actions-1'));
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('keeps a disabled action visible with its reason', () => {
    const onSelect = vi.fn();
    renderActions([
      {
        key: 'drop',
        label: 'Drop',
        onSelect,
        disabled: true,
        hint: 'Needs one member',
      },
    ]);
    openMenu();
    const item = screen.getByRole('menuitem', { name: /Drop/ });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).toHaveTextContent('Needs one member');
    fireEvent.click(item);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('disables the trigger', () => {
    renderActions([{ key: 'edit', label: 'Edit', onSelect: vi.fn() }], {
      disabled: true,
    });
    expect(screen.getByTestId('row-actions-1')).toBeDisabled();
  });

  it('renders nothing without actions', () => {
    renderActions([]);
    expect(screen.queryByTestId('row-actions-1')).toBeNull();
  });
});

describe('DataTableRowActions inline from a breakpoint', () => {
  let restore: () => void = () => undefined;
  afterEach(() => restore());

  const actions = (onSelect = vi.fn()): DataTableRowAction[] => [
    { key: 'edit', label: 'Edit', onSelect, testId: 'edit-1' },
    {
      key: 'drop',
      label: 'Drop',
      onSelect: vi.fn(),
      destructive: true,
      disabled: true,
      hint: 'Needs one member',
      testId: 'drop-1',
    },
  ];

  it('shows inline buttons and no menu trigger at desktop width', () => {
    restore = setViewportWidth(1280);
    renderActions(actions(), { inlineFrom: 'md' });
    const group = screen.getByTestId('row-actions-1');
    expect(group).toHaveAttribute('role', 'group');
    expect(group).toHaveAccessibleName('Actions for Alpha');
    expect(screen.getByTestId('edit-1').tagName).toBe('BUTTON');
    expect(
      screen.queryByRole('button', { name: 'Actions for Alpha' }),
    ).toBeNull();
    expect(document.querySelector('[aria-haspopup="menu"]')).toBeNull();
  });

  it('shows only the menu trigger below the breakpoint', () => {
    restore = setViewportWidth(390);
    renderActions(actions(), { inlineFrom: 'md' });
    expect(screen.getByTestId('row-actions-1')).toHaveAttribute(
      'aria-haspopup',
      'menu',
    );
    expect(screen.queryByTestId('edit-1')).toBeNull();
  });

  it('runs an inline action without reaching the row', () => {
    restore = setViewportWidth(1280);
    const onSelect = vi.fn();
    const onRowClick = vi.fn();
    renderActions(actions(onSelect), { inlineFrom: 'md', onRowClick });
    fireEvent.click(screen.getByTestId('edit-1'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('keeps a disabled inline action with its reason as the description', () => {
    restore = setViewportWidth(1280);
    renderActions(actions(), { inlineFrom: 'md' });
    const drop = screen.getByTestId('drop-1');
    expect(drop).toBeDisabled();
    expect(drop).toHaveClass('bg-destructive/60');
    expect(drop.parentElement).toHaveAccessibleDescription('Needs one member');
  });

  it('disables every inline button', () => {
    restore = setViewportWidth(1280);
    renderActions(actions(), { inlineFrom: 'md', disabled: true });
    expect(screen.getByTestId('edit-1')).toBeDisabled();
  });
});
