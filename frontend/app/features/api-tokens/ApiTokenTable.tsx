import { useMemo, type ReactNode } from 'react';

import { DataTable } from '~/components/ui/data-table';
import {
  DEFAULT_API_TOKEN_COLUMNS,
  makeApiTokenColumns,
  type ApiTokenColumnId,
} from './apiTokenColumns';
import type { ApiToken } from './schemas';

export interface ApiTokenTableProps {
  tokens: ApiToken[];
  testIdPrefix?: string;
  columns?: readonly ApiTokenColumnId[];
  canRevoke?: (token: ApiToken) => boolean;
  onRevoke?: (token: ApiToken) => void;
  revoking?: boolean;
  toolbarActions?: ReactNode;
  emptyMessage?: string;
}

export function ApiTokenTable({
  tokens,
  testIdPrefix = 'api-token',
  columns = DEFAULT_API_TOKEN_COLUMNS,
  canRevoke,
  onRevoke,
  revoking = false,
  toolbarActions,
  emptyMessage = 'No tokens yet',
}: ApiTokenTableProps) {
  const cols = useMemo(
    () =>
      makeApiTokenColumns({
        testIdPrefix,
        columns,
        canRevoke,
        onRevoke,
        revoking,
      }),
    [testIdPrefix, columns, canRevoke, onRevoke, revoking],
  );
  return (
    <DataTable
      columns={cols}
      data={tokens}
      getRowId={(t) => t.id}
      getRowTestId={(t) => `${testIdPrefix}-row-${t.id}`}
      initialSorting={[{ id: 'created', desc: true }]}
      // The table fits the settings panel; the token cell shows the creation
      // time, which leaves the name room beside each token's operations.
      initialColumnVisibility={{ created: false }}
      toolbarActions={toolbarActions}
      emptyMessage={emptyMessage}
      data-testid={`${testIdPrefix}-table`}
    />
  );
}
