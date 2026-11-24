import { useMemo, type ReactNode } from 'react';

import type { SignupHistoryEntry } from '~/components/events/schemas';
import { DataTable } from '~/components/ui/data-table';

import {
  DEFAULT_SIGNUP_HISTORY_COLUMNS,
  makeSignupHistoryColumns,
  type SignupHistoryColumnId,
} from './signupHistoryColumns';

export type { SignupHistoryColumnId } from './signupHistoryColumns';

// Pages come from the server cursor; DataTable must never paginate them client-side.
export const HISTORY_TABLE_PAGE_SIZE = Number.MAX_SAFE_INTEGER;

const COMPACT_VISIBILITY = { when: false, actor: false, means: false };

export interface SignupHistoryTableProps {
  rows: SignupHistoryEntry[];
  columns?: readonly SignupHistoryColumnId[];
  eventTimezone?: string;
  compact?: boolean;
  originalId?: number | null;
  emptyMessage?: ReactNode;
}

/** The signup ledger table: DataTable over makeSignupHistoryColumns, newest first. */
export function SignupHistoryTable({
  rows,
  columns = DEFAULT_SIGNUP_HISTORY_COLUMNS,
  eventTimezone,
  compact = false,
  originalId = null,
  emptyMessage,
}: SignupHistoryTableProps) {
  const loadedById = useMemo(
    () => new Map(rows.map((e) => [e.id, e] as const)),
    [rows],
  );
  const cols = useMemo(
    () =>
      makeSignupHistoryColumns({
        columns,
        eventTimezone,
        compact,
        loadedById,
        originalId,
      }),
    [columns, eventTimezone, compact, loadedById, originalId],
  );
  return (
    <DataTable
      columns={cols}
      data={rows}
      getRowId={(e) => e.id}
      getRowTestId={(e) => `signup-history-row-${e.id}`}
      initialColumnVisibility={compact ? COMPACT_VISIBILITY : undefined}
      pageSize={HISTORY_TABLE_PAGE_SIZE}
      emptyMessage={emptyMessage}
    />
  );
}
