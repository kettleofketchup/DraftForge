import { useEffect, useRef } from 'react';
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
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { attendanceRowKey, type WalkIn } from './attendanceDraft';
import { formatShowRate } from './format';
import { OutcomeChip } from './OutcomeChip';
import {
  ATTENDANCE_FLAG_LABELS,
  OUTCOME_LABELS,
  SOURCE_LABELS,
  STAFF_SETTABLE_OUTCOMES,
  VIRTUAL_OUTCOME_LABEL,
  WALK_IN_LABEL,
  type AttendanceRow,
  type Outcome,
  type StaffSettableOutcome,
} from './schemas';

export interface AttendanceTableRow extends AttendanceRow {
  key: string;
  provisional: boolean;
}

export function toAttendanceTableRow(row: AttendanceRow): AttendanceTableRow {
  return { ...row, key: attendanceRowKey(row), provisional: false };
}

export function walkInTableRow(walkIn: WalkIn): AttendanceTableRow {
  return {
    member: {
      org_user_pk: null,
      user_pk: walkIn.user_pk,
      username: walkIn.username,
      nickname: walkIn.nickname,
      avatarUrl: walkIn.avatarUrl,
    },
    org_user_pk: null,
    signup_status: null,
    outcome: 'attended',
    source: 'staff',
    committed: false,
    virtual: false,
    finalized: false,
    voided: false,
    flag: null,
    set_by: null,
    reason: '',
    show_rate: 0,
    status: 'new',
    key: `walkin-${walkIn.user_pk}`,
    provisional: true,
  };
}

export type AttendanceColumnId =
  | 'select'
  | 'member'
  | 'outcome'
  | 'source'
  | 'flag'
  | 'rate';

export const DEFAULT_ATTENDANCE_COLUMNS: readonly AttendanceColumnId[] = [
  'select',
  'member',
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
  onToggle: (key: string, checked: boolean) => void;
  onToggleAll: (checked: boolean) => void;
  outcomeFor: (row: AttendanceTableRow) => Outcome;
  onOutcomeChange: (key: string, outcome: StaffSettableOutcome) => void;
  onRemoveWalkIn: (userPk: number) => void;
  columns?: readonly AttendanceColumnId[];
}

const CHECKBOX_CLASS = 'size-4 shrink-0 accent-primary';
const CHECKBOX_LABEL_CLASS =
  'flex min-h-11 cursor-pointer items-center sm:min-h-9';

function isSettable(outcome: Outcome): outcome is StaffSettableOutcome {
  return (STAFF_SETTABLE_OUTCOMES as readonly Outcome[]).includes(outcome);
}

function isDefaulted(row: AttendanceTableRow, outcome: Outcome): boolean {
  return row.virtual && row.flag == null && outcome === 'pending';
}

function rateText(row: AttendanceTableRow): string {
  return row.provisional ? '—' : formatShowRate(row);
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
    <label className={CHECKBOX_LABEL_CLASS}>
      <input
        ref={ref}
        type="checkbox"
        aria-label="Select all members"
        data-testid={testId}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className={CHECKBOX_CLASS}
      />
    </label>
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
          <label className={CHECKBOX_LABEL_CLASS}>
            <input
              type="checkbox"
              aria-label={`Select ${DisplayName(r.member)}`}
              data-testid={`${testIdPrefix}-select-${r.key}`}
              checked={selected.has(r.key)}
              onChange={(e) => onToggle(r.key, e.target.checked)}
              className={CHECKBOX_CLASS}
            />
          </label>
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
              <span className="font-medium break-words">
                {DisplayName(r.member)}
              </span>
              <span
                className="text-xs text-muted-foreground sm:hidden"
                data-testid={`${testIdPrefix}-stacked-${r.key}`}
              >
                {r.committed ? SOURCE_LABELS[r.source] : WALK_IN_LABEL}
                {' · '}
                {rateText(r)}
              </span>
              {r.flag && (
                <span
                  className="text-xs text-warning md:hidden"
                  data-testid={`${testIdPrefix}-stacked-flag-${r.key}`}
                >
                  {ATTENDANCE_FLAG_LABELS[r.flag]}
                </span>
              )}
            </div>
          </div>
        );
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
        const defaulted = isDefaulted(r, outcome);
        if (r.provisional) {
          return (
            <div className="flex items-center gap-1" data-testid={testId}>
              <OutcomeChip outcome="attended" />
              <RemoveIconButton
                label={`Remove walk-in ${DisplayName(r.member)}`}
                data-testid={`${testIdPrefix}-walkin-remove-${r.member.user_pk}`}
                onClick={() => onRemoveWalkIn(r.member.user_pk)}
              />
            </div>
          );
        }
        if (!editable) {
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
            value={isSettable(outcome) && !defaulted ? outcome : ''}
            onValueChange={(v) =>
              onOutcomeChange(r.key, v as StaffSettableOutcome)
            }
          >
            <BrandSelectTrigger
              size="sm"
              className="min-h-11 w-full sm:min-h-9"
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
      meta: { headClassName: 'w-40 sm:w-44', cellClassName: 'w-40 sm:w-44' },
    },
    source: {
      id: 'source',
      enableSorting: false,
      header: 'Source',
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div
            className="flex flex-wrap items-center gap-1"
            data-testid={`${testIdPrefix}-source-${r.key}`}
          >
            <span className="text-muted-foreground">
              {SOURCE_LABELS[r.source]}
            </span>
            {!r.committed && <Badge variant="outline">{WALK_IN_LABEL}</Badge>}
          </div>
        );
      },
      meta: {
        headClassName: 'hidden w-28 sm:table-cell',
        cellClassName: 'hidden w-28 sm:table-cell',
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
            className="border-warning/30 bg-warning/20 whitespace-normal text-warning"
            data-testid={`${testIdPrefix}-flag-${r.key}`}
          >
            {ATTENDANCE_FLAG_LABELS[r.flag]}
          </Badge>
        );
      },
      meta: {
        headClassName: 'hidden w-48 md:table-cell',
        cellClassName: 'hidden w-48 md:table-cell',
      },
    },
    rate: {
      id: 'rate',
      accessorFn: (r) => (r.provisional ? -1 : r.show_rate),
      sortDescFirst: true,
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Show rate" />
      ),
      cell: ({ row }) => rateText(row.original),
      meta: {
        headClassName: 'hidden w-20 text-right sm:table-cell',
        cellClassName: 'hidden w-20 text-right tabular-nums sm:table-cell',
      },
    },
  };
  const ids = editable ? columns : columns.filter((id) => id !== 'select');
  return ids.map((id) => all[id]);
}
