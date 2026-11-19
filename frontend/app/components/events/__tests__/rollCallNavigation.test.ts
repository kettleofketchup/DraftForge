import { describe, expect, it } from 'vitest';
import {
  defaultRollCallFocus,
  moveRollCallFocus,
  resolveRollCallFocus,
  rollCallFocusAfterAction,
  rollCallRowActions,
  splitRollCallRows,
} from '../rollCallNavigation';
import type { EventSignupType } from '../schemas';

function signup(id: number, status: string): EventSignupType {
  return { id, status } as unknown as EventSignupType;
}

const ids = (list: EventSignupType[]) => list.map((s) => s.id);

const rows = splitRollCallRows([
  signup(1, 'approved'),
  signup(2, 'confirmed'),
  signup(3, 'rejected'),
  signup(4, 'approved'),
  signup(5, 'rsvp'),
  signup(6, 'approved'),
]);

describe('splitRollCallRows', () => {
  it('orders rows confirmed, awaiting, others', () => {
    expect(ids(rows.confirmed)).toEqual([2]);
    expect(ids(rows.awaiting)).toEqual([1, 4, 6]);
    expect(ids(rows.others)).toEqual([3, 5]);
    expect(ids(rows.ordered)).toEqual([2, 1, 4, 6, 3, 5]);
  });
});

describe('rollCallRowActions', () => {
  it.each([
    ['approved', 'confirm', 'reject'],
    ['confirmed', null, 'cancel'],
    ['rsvp', 'approve', 'reject'],
    ['pending_approval', 'approve', 'reject'],
    ['waitlisted', 'approve', 'reject'],
    ['rejected', 'restore', null],
    ['cancelled', 'restore', null],
    ['dropped', null, null],
  ])('%s → primary %s, remove %s', (status, primary, remove) => {
    expect(rollCallRowActions(status)).toEqual({ primary, remove });
  });
});

describe('focus', () => {
  it('defaults to the first awaiting row', () => {
    expect(defaultRollCallFocus(rows)).toBe(1);
  });

  it('falls back to the first row when nothing is awaiting', () => {
    const noAwaiting = splitRollCallRows([
      signup(2, 'confirmed'),
      signup(3, 'rejected'),
    ]);
    expect(defaultRollCallFocus(noAwaiting)).toBe(2);
    expect(defaultRollCallFocus(splitRollCallRows([]))).toBeNull();
  });

  it('keeps a selection that still exists and replaces one that does not', () => {
    expect(resolveRollCallFocus(rows, 5)).toBe(5);
    expect(resolveRollCallFocus(rows, 99)).toBe(1);
    expect(resolveRollCallFocus(rows, null)).toBe(1);
  });

  it('moves in on-screen order and clamps at both ends', () => {
    expect(moveRollCallFocus(rows, 1, 1)).toBe(4);
    expect(moveRollCallFocus(rows, 1, -1)).toBe(2);
    expect(moveRollCallFocus(rows, 2, -1)).toBe(2);
    expect(moveRollCallFocus(rows, 5, 1)).toBe(5);
    expect(moveRollCallFocus(rows, 99, 1)).toBe(1);
  });
});

describe('rollCallFocusAfterAction', () => {
  it('advances to the next row in the same section', () => {
    expect(rollCallFocusAfterAction(rows, 1)).toBe(4);
    expect(rollCallFocusAfterAction(rows, 4)).toBe(6);
  });

  it('steps back when the acted row was last in its section', () => {
    expect(rollCallFocusAfterAction(rows, 6)).toBe(4);
    expect(rollCallFocusAfterAction(rows, 5)).toBe(3);
  });

  it('jumps to the awaiting list when the section empties', () => {
    expect(rollCallFocusAfterAction(rows, 2)).toBe(1);
  });

  it('returns null when nothing else is left', () => {
    const lone = splitRollCallRows([signup(1, 'approved')]);
    expect(rollCallFocusAfterAction(lone, 1)).toBeNull();
  });
});
