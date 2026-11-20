// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DataTableRowActions, type DataTableRowAction } from '..';

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
  props: { disabled?: boolean; onRowClick?: () => void } = {},
) {
  render(
    <div onClick={props.onRowClick}>
      <DataTableRowActions
        label="Actions for Alpha"
        actions={actions}
        disabled={props.disabled}
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
