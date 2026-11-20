import type { ReactNode } from 'react';

import type { TeamAction } from '~/components/api/teamManagementAPI';

/** An action the roster UI wants to run; the dialog asks for a reason first. */
export type PendingTeamAction = {
  action: TeamAction;
  title: string;
  summary: ReactNode;
  confirmText: string;
  destructive?: boolean;
  warning?: ReactNode;
  withReplacing?: boolean;
};
