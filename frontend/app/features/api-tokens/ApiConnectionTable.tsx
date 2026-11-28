import { useMemo, type ReactNode } from 'react';

import { DataTable } from '~/components/ui/data-table';
import {
  DEFAULT_API_CONNECTION_COLUMNS,
  makeApiConnectionColumns,
  type ApiConnectionColumnId,
} from './apiConnectionColumns';
import type { ApiConnection } from './connectionSchemas';

export interface ApiConnectionTableProps {
  connections: ApiConnection[];
  testIdPrefix?: string;
  columns?: readonly ApiConnectionColumnId[];
  onManage?: (row: ApiConnection) => void;
  toolbarActions?: ReactNode;
  emptyMessage?: string;
}

export function ApiConnectionTable({
  connections,
  testIdPrefix = 'api-connection',
  columns = DEFAULT_API_CONNECTION_COLUMNS,
  onManage,
  toolbarActions,
  emptyMessage = 'No connections yet',
}: ApiConnectionTableProps) {
  const cols = useMemo(
    () => makeApiConnectionColumns({ testIdPrefix, columns, onManage }),
    [testIdPrefix, columns, onManage],
  );
  return (
    <DataTable
      columns={cols}
      data={connections}
      getRowId={(c) => c.id}
      getRowTestId={(c) => `${testIdPrefix}-row-${c.id}`}
      initialSorting={[{ id: 'name', desc: false }]}
      toolbarActions={toolbarActions}
      emptyMessage={emptyMessage}
      data-testid={`${testIdPrefix}-table`}
    />
  );
}
