import { useCallback, useState } from 'react';
import type { DraftResetReport } from '~/components/api/types';
import { DraftResetSummaryDialog } from '../DraftResetSummaryDialog';

/** Holds the last reset report that dropped or kept teams, and its dialog. */
export function useDraftResetSummary() {
  const [report, setReport] = useState<DraftResetReport | null>(null);
  const showResetSummary = useCallback(
    (next: DraftResetReport) => setReport(next),
    [],
  );
  const resetSummaryDialog = (
    <DraftResetSummaryDialog
      report={report}
      onOpenChange={(open) => {
        if (!open) setReport(null);
      }}
    />
  );
  return { showResetSummary, resetSummaryDialog };
}
