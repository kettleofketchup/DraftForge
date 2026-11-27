import { useMemo, type ReactNode } from 'react';
import type { DiscordPreviewOptions } from '~/components/discord/timestamps';
import { DataTable, type DataTableSearch } from '~/components/ui/data-table';
import {
  DEFAULT_PROMOTION_COLUMNS,
  candidateRowId,
  makePromotionColumns,
  type ComposeMode,
  type PromotionColumnId,
} from './promotionColumns';
import type { CandidateRow, CandidateSource } from './schemas';

export type { ComposeMode, PromotionColumnId } from './promotionColumns';

export interface PromotionTableProps {
  rows: CandidateRow[];
  source: CandidateSource;
  poolN: number;
  previewOptions: DiscordPreviewOptions;
  onCompose: (row: CandidateRow, mode: ComposeMode) => void;
  onUndo: (sendId: number) => void;
  onCopyHandle: (handle: string) => void;
  pendingRowId?: string | null;
  undoPending?: boolean;
  hideUndoFor?: number | null;
  /** Server-side player search, shown in the table toolbar. */
  search?: DataTableSearch;
  toolbarStart?: ReactNode;
  /** Test id namespace: the table is `${prefix}-table`, rows `${prefix}-row-<id>`. */
  testIdPrefix?: string;
  columns?: readonly PromotionColumnId[];
  emptyMessage?: ReactNode;
  pageSize?: number;
}

/** The shared promotion audience table: DataTable over makePromotionColumns. */
export function PromotionTable({
  rows,
  source,
  poolN,
  previewOptions,
  onCompose,
  onUndo,
  onCopyHandle,
  pendingRowId = null,
  undoPending = false,
  hideUndoFor = null,
  search,
  toolbarStart,
  testIdPrefix = 'promo-candidate',
  columns = DEFAULT_PROMOTION_COLUMNS,
  emptyMessage = 'No players match.',
  pageSize = 25,
}: PromotionTableProps) {
  const cols = useMemo(
    () =>
      makePromotionColumns({
        source,
        poolN,
        previewOptions,
        onCompose,
        onUndo,
        onCopyHandle,
        pendingRowId,
        undoPending,
        hideUndoFor,
        testIdPrefix,
        columns,
      }),
    [
      source,
      poolN,
      previewOptions,
      onCompose,
      onUndo,
      onCopyHandle,
      pendingRowId,
      undoPending,
      hideUndoFor,
      testIdPrefix,
      columns,
    ],
  );
  return (
    <DataTable
      columns={cols}
      data={rows}
      getRowId={candidateRowId}
      getRowTestId={(r) => `${testIdPrefix}-row-${candidateRowId(r)}`}
      enableToolbar={search != null}
      search={search}
      toolbarStart={toolbarStart}
      toolbarTestIdPrefix={testIdPrefix}
      pageSize={pageSize}
      emptyMessage={emptyMessage}
      data-testid={`${testIdPrefix}-table`}
    />
  );
}
