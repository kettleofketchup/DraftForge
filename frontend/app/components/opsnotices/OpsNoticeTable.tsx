import { useMemo } from 'react';

import type { OpsNotice } from '~/components/api/opsNoticesAPI';
import { DataTable } from '~/components/ui/data-table';

import {
  DEFAULT_OPS_NOTICE_COLUMNS,
  makeOpsNoticeColumns,
  type OpsNoticeColumnId,
} from './opsNoticeColumns';

export type { OpsNoticeColumnId } from './opsNoticeColumns';

export interface OpsNoticeTableProps {
  notices: OpsNotice[];
  /** Test id namespace: the table is `${prefix}-table`, rows `${prefix}-row-<id>`. */
  testIdPrefix?: string;
  columns?: readonly OpsNoticeColumnId[];
  sortable?: boolean;
  /** Filter bar: severity/type/event facets, notice search and a Columns menu. */
  filters?: boolean;
  noticeHref?: (n: OpsNotice) => string;
  onResolve?: (n: OpsNotice) => void;
  resolving?: boolean;
  onRowClick?: (n: OpsNotice) => void;
  pageSize?: number;
  density?: 'default' | 'compact';
  emptyMessage?: string;
  scrollX?: boolean;
}

const NOTICE_SEARCH = { label: 'Search', placeholder: 'Search notices' };

/** The shared operations-notice table: DataTable over makeOpsNoticeColumns. */
export function OpsNoticeTable({
  notices,
  testIdPrefix = 'ops-notice',
  columns = DEFAULT_OPS_NOTICE_COLUMNS,
  sortable = true,
  filters = false,
  noticeHref,
  onResolve,
  resolving = false,
  onRowClick,
  pageSize = 25,
  density = 'default',
  emptyMessage = 'No open notices',
  scrollX = false,
}: OpsNoticeTableProps) {
  const cols = useMemo(
    () =>
      makeOpsNoticeColumns({
        testIdPrefix,
        columns,
        sortable,
        noticeHref,
        onResolve,
        resolving,
      }),
    [testIdPrefix, columns, sortable, noticeHref, onResolve, resolving],
  );
  return (
    <DataTable
      columns={cols}
      data={notices}
      getRowId={(n) => n.id}
      getRowTestId={(n) => `${testIdPrefix}-row-${n.id}`}
      onRowClick={onRowClick}
      initialSorting={
        columns.includes('severity') ? [{ id: 'severity', desc: true }] : []
      }
      enableToolbar={filters}
      globalSearch={filters ? NOTICE_SEARCH : undefined}
      toolbarTestIdPrefix={testIdPrefix}
      pageSize={pageSize}
      density={density}
      emptyMessage={emptyMessage}
      scrollX={scrollX}
      scrollTestId={scrollX ? `${testIdPrefix}-scroll` : undefined}
      scrollLabel={scrollX ? 'Operations notices' : undefined}
      data-testid={`${testIdPrefix}-table`}
    />
  );
}
