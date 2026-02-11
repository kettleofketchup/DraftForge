import type { EntityContext } from '~/components/user/AddUserModal/types';

export interface CSVRow {
  steam_friend_id?: string;
  discord_id?: string;
  discord_username?: string;
  name?: string;
  mmr?: string;
  team_name?: string;
  team_captain?: string;
  positions?: string;
}

export type RowStatus = 'valid' | 'error';

export interface ValidatedRow {
  index: number;
  raw: CSVRow;
  status: RowStatus;
  message?: string;
}

export interface CSVImportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityContext: EntityContext;
  onComplete: () => void;
}

export type ImportStep = 'upload' | 'preview' | 'results';
