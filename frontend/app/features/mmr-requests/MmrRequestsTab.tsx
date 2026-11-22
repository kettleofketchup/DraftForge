import { AlertCircle, BadgeCheck } from 'lucide-react';
import { useState } from 'react';
import { Alert, AlertDescription } from '~/components/ui/alert';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { MobileNavDropdown } from '~/components/ui/mobile-nav-dropdown';
import { Spinner } from '~/components/ui/spinner';
import { Tabs, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { MmrRequestCard } from './MmrRequestCard';
import { useMmrPendingCount, useMmrQueue } from './queries';
import type { MmrScope } from './queryKeys';
import type { MmrQueueStatus } from './schemas';
import { SetOfficialMmrDialog } from './SetOfficialMmrDialog';

export interface MmrRequestsTabProps {
  scope: MmrScope;
}

const STATUS_OPTIONS: { value: MmrQueueStatus; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'superseded', label: 'Superseded' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'all', label: 'All' },
];

export function MmrRequestsTab({ scope }: MmrRequestsTabProps) {
  const [status, setStatus] = useState<MmrQueueStatus>('pending');
  const [setOfficialOpen, setSetOfficialOpen] = useState(false);
  const queue = useMmrQueue(scope, status);
  const pendingCount = useMmrPendingCount(scope).data?.count ?? 0;
  const rows = queue.data ?? [];
  const label =
    STATUS_OPTIONS.find((o) => o.value === status)?.label.toLowerCase() ?? '';

  return (
    <div className="space-y-4" data-testid="mmr-requests-tab">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">MMR requests</h2>
        <SecondaryButton
          size="sm"
          onClick={() => setSetOfficialOpen(true)}
          data-testid="set-official-mmr-open"
        >
          <BadgeCheck className="mr-2 size-4" />
          Set official MMR
        </SecondaryButton>
      </div>

      <Tabs
        value={status}
        onValueChange={(v) => setStatus(v as MmrQueueStatus)}
      >
        <MobileNavDropdown
          options={STATUS_OPTIONS}
          value={status}
          onValueChange={(v) => setStatus(v as MmrQueueStatus)}
          variant="secondary"
          className="mb-4 md:hidden"
        />
        <TabsList
          className="hidden md:flex"
          data-testid="mmr-queue-status-filter"
        >
          {STATUS_OPTIONS.map((option) => (
            <TabsTrigger
              key={option.value}
              value={option.value}
              className="gap-2"
              data-testid={`mmr-queue-status-${option.value}`}
            >
              {option.label}
              {option.value === 'pending' && pendingCount > 0 && (
                <Badge variant="secondary" className="text-xs">
                  {pendingCount}
                </Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {queue.isLoading ? (
        <div
          className="flex items-center justify-center py-8"
          data-testid="mmr-queue-loading"
        >
          <Spinner className="size-8" />
        </div>
      ) : queue.isError ? (
        <Alert variant="destructive" data-testid="mmr-queue-error">
          <AlertCircle />
          <AlertDescription>Failed to load MMR requests</AlertDescription>
        </Alert>
      ) : rows.length === 0 ? (
        <Alert data-testid="mmr-queue-empty">
          <AlertDescription>
            {status === 'all'
              ? 'No MMR requests yet'
              : `No ${label} MMR requests`}
          </AlertDescription>
        </Alert>
      ) : (
        <div className="space-y-3" data-testid="mmr-queue-list">
          {rows.map((request) => (
            <MmrRequestCard key={request.id} request={request} scope={scope} />
          ))}
        </div>
      )}

      <SetOfficialMmrDialog
        scope={scope}
        open={setOfficialOpen}
        onOpenChange={setSetOfficialOpen}
      />
    </div>
  );
}
