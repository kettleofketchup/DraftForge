import { useEffect, useRef } from 'react';
import { EventStateBadge } from '~/components/events/EventStateBadge';
import { Badge } from '~/components/ui/badge';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectGroup,
  SelectValue,
} from '~/components/ui/brand-select';
import { RemoveIconButton } from '~/components/ui/buttons';
import {
  DataTableColumnHeader,
  type AppColumnDef,
} from '~/components/ui/data-table';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { OutcomeChip } from './OutcomeChip';
import {
  OUTCOME_LABELS,
  SOURCE_LABELS,
  STAFF_SETTABLE_OUTCOMES,
  WALK_IN_LABEL,
  type AttendanceFlag,
  type AttendanceRow,
  type Outcome,
  type StaffSettableOutcome,
} from './schemas';
import { scoreLabel } from './scoring';

export const ATTENDANCE_FLAG_LABELS: Record<AttendanceFlag, string> = {
  roll_call_unconfirmed: 'Did not confirm at roll call',
  dropped_unattributed: 'Dropped, needs review',
};

export const VIRTUAL_OUTCOME_LABEL = 'Attended (default)';

export interface AttendanceTableRow extends AttendanceRow {
  /** Test-id and row-id key: org_user_pk, `user-<pk>` or `walkin-<pk>`. */
  key: string;
  /** A walk-in added in this session, not yet saved. */
  provisional: boolean;
}

export function attendanceRowKey(row: AttendanceRow): string {
  return row.org_user_pk != null
    ? String(row.org_user_pk)
    : `user-${row.member.user_pk}`;
}

export function toAttendanceTableRow(row: AttendanceRow): AttendanceTableRow {
  return { ...row, key: attendanceRowKey(row), provisional: false };
}

export type AttendanceColumnId =
  | 'select'
  | 'member'
  | 'signup'
  | 'outcome'
  | 'source'
  | 'flag'
  | 'rate';

export const DEFAULT_ATTENDANCE_COLUMNS: readonly AttendanceColumnId[] = [
  'select',
  'member',
  'signup',
  'outcome',
  'source',
  'flag',
  'rate',
];

export interface MakeAttendanceColumnsOptions {
  testIdPrefix: string;
  editable: boolean;
  selected: ReadonlySet<string>;
  selectableKeys: readonly string[];
  onToggle: (rowKey: string, checked: boolean) => void;
  onToggleAll: (checked: boolean) => void;
  outcomeFor: (row: AttendanceTableRow) => Outcome;
  onOutcomeChange: (rowKey: string, outcome: StaffSettableOutcome) => void;
  onRemoveWalkIn: (userPk: number) => void;
  columns?: readonly AttendanceColumnId[];
}

function isSettable(outcome: Outcome): outcome is StaffSettableOutcome {
  return (STAFF_SETTABLE_OUTCOMES as readonly Outcome[]).includes(outcome);
}

function SelectAllCheckbox({
  checked,
  indeterminate,
  disabled,
  onChange,
  testId,
}: {
  checked: boolean;
  indeterminate: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
  testId: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label="Select all members"
      data-testid={testId}
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
      className="size-4 shrink-0 rounded border-border accent-primary"
    />
  );
}

export function makeAttendanceColumns({
  testIdPrefix,
  editable,
  selected,
  selectableKeys,
  onToggle,
  onToggleAll,
  outcomeFor,
  onOutcomeChange,
  onRemoveWalkIn,
  columns = DEFAULT_ATTENDANCE_COLUMNS,
}: MakeAttendanceColumnsOptions): AppColumnDef<AttendanceTableRow>[] {
  const selectedCount = selectableKeys.filter((key) =>
    selected.has(key),
  ).length;
  const allSelected =
    selectableKeys.length > 0 && selectedCount === selectableKeys.length;

  const all: Record<AttendanceColumnId, AppColumnDef<AttendanceTableRow>> = {
    select: {
      id: 'select',
      enableSorting: false,
      header: () => (
        <SelectAllCheckbox
          checked={allSelected}
          indeterminate={selectedCount > 0 && !allSelected}
          disabled={selectableKeys.length === 0}
          onChange={onToggleAll}
          testId={`${testIdPrefix}-select-all`}
        />
      ),
      cell: ({ row }) => {
        const r = row.original;
        if (r.provisional) return null;
        return (
          <input
            type="checkbox"
            aria-label={`Select ${DisplayName(r.member)}`}
            data-testid={`${testIdPrefix}-select-${r.key}`}
            checked={selected.has(r.key)}
            onChange={(e) => onToggle(r.key, e.target.checked)}
            className="size-4 shrink-0 rounded border-border accent-primary"
          />
        );
      },
      meta: { headClassName: 'w-10', cellClassName: 'w-10' },
    },
    member: {
      id: 'member',
      accessorFn: (r) => DisplayName(r.member).toLocaleLowerCase(),
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Member" />
      ),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex min-w-0 items-center gap-2">
            <UserAvatar
              user={{ ...r.member, pk: r.member.user_pk }}
              size="sm"
            />
            <div className="flex min-w-0 flex-col">
              <span className="wrap-anywhere font-medium">
                {DisplayName(r.member)}
              </span>
              <span className="text-xs text-muted-foreground md:hidden">
                {r.provisional ? '—' : scoreLabel(r)}
              </span>
            </div>
            {r.provisional && (
              <RemoveIconButton
                label={`Remove walk-in ${DisplayName(r.member)}`}
                data-testid={`${testIdPrefix}-walkin-remove-${r.member.user_pk}`}
                onClick={() => onRemoveWalkIn(r.member.user_pk)}
              />
            )}
          </div>
        );
      },
    },
    signup: {
      id: 'signup',
      accessorFn: (r) => r.signup_status ?? '',
      enableSorting: false,
      header: 'Signup',
      cell: ({ row }) =>
        row.original.signup_status ? (
          <EventStateBadge state={row.original.signup_status} />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
      meta: {
        headClassName: 'hidden w-28 lg:table-cell',
        cellClassName: 'hidden w-28 lg:table-cell',
      },
    },
    outcome: {
      id: 'outcome',
      enableSorting: false,
      header: 'Outcome',
      cell: ({ row }) => {
        const r = row.original;
        const testId = `${testIdPrefix}-outcome-${r.key}`;
        const outcome = outcomeFor(r);
        const defaulted = r.virtual && outcome === 'pending';
        if (!editable || r.provisional) {
          return (
            <span data-testid={testId}>
              {defaulted ? (
                <span className="text-sm text-muted-foreground">
                  {VIRTUAL_OUTCOME_LABEL}
                </span>
              ) : (
                <OutcomeChip outcome={outcome} />
              )}
            </span>
          );
        }
        const label = defaulted
          ? VIRTUAL_OUTCOME_LABEL
          : OUTCOME_LABELS[outcome];
        return (
          <BrandSelect
            value={isSettable(outcome) ? outcome : ''}
            onValueChange={(v) =>
              onOutcomeChange(r.key, v as StaffSettableOutcome)
            }
          >
            <BrandSelectTrigger
              size="sm"
              className="w-full"
              data-testid={testId}
              aria-label={`Outcome for ${DisplayName(r.member)}`}
            >
              <SelectValue placeholder={label}>{label}</SelectValue>
            </BrandSelectTrigger>
            <BrandSelectContent>
              <SelectGroup>
                {STAFF_SETTABLE_OUTCOMES.map((value) => (
                  <BrandSelectItem
                    key={value}
                    value={value}
                    data-testid={`${testIdPrefix}-outcome-option-${value}`}
                  >
                    {OUTCOME_LABELS[value]}
                  </BrandSelectItem>
                ))}
              </SelectGroup>
            </BrandSelectContent>
          </BrandSelect>
        );
      },
      meta: { headClassName: 'w-44', cellClassName: 'w-44' },
    },
    source: {
      id: 'source',
      enableSorting: false,
      header: 'Source',
      cell: ({ row }) => {
        const r = row.original;
        if (!r.committed) {
          return (
            <Badge
              variant="outline"
              className="border-info/30 bg-info/20 text-info"
              data-testid={`${testIdPrefix}-source-${r.key}`}
            >
              {WALK_IN_LABEL}
            </Badge>
          );
        }
        if (r.virtual) return null;
        return (
          <Badge
            variant="outline"
            className="border-border bg-muted text-muted-foreground"
            data-testid={`${testIdPrefix}-source-${r.key}`}
          >
            {SOURCE_LABELS[r.source]}
          </Badge>
        );
      },
      meta: {
        headClassName: 'hidden w-28 md:table-cell',
        cellClassName: 'hidden w-28 md:table-cell',
      },
    },
    flag: {
      id: 'flag',
      enableSorting: false,
      header: 'Flag',
      cell: ({ row }) => {
        const r = row.original;
        if (!r.flag) return null;
        return (
          <Badge
            variant="outline"
            className="whitespace-normal border-warning/30 bg-warning/20 text-warning"
            data-testid={`${testIdPrefix}-flag-${r.key}`}
          >
            {ATTENDANCE_FLAG_LABELS[r.flag]}
          </Badge>
        );
      },
      meta: { headClassName: 'w-36', cellClassName: 'w-36' },
    },
    rate: {
      id: 'rate',
      accessorFn: (r) => (r.provisional ? -1 : r.show_rate),
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Show rate" />
      ),
      cell: ({ row }) =>
        row.original.provisional ? '—' : scoreLabel(row.original),
      meta: {
        headClassName: 'hidden w-24 text-right md:table-cell',
        cellClassName:
          'hidden w-24 text-right font-semibold tabular-nums md:table-cell',
      },
    },
  };
  const ids = editable ? columns : columns.filter((id) => id !== 'select');
  return ids.map((id) => all[id]);
}
