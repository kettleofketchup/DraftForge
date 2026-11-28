import { Download } from 'lucide-react';
import { useState } from 'react';
import { SecondaryButton } from '~/components/ui/buttons';
import { ExportSignupRecordsDialog } from './ExportSignupRecordsDialog';

export interface ExportSignupRecordsButtonProps {
  orgId: number;
}

export function ExportSignupRecordsButton({
  orgId,
}: ExportSignupRecordsButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <SecondaryButton
        size="sm"
        data-testid="export-signup-records-button"
        onClick={() => setOpen(true)}
      >
        <Download className="h-4 w-4" />
        Export sign-up records
      </SecondaryButton>
      <ExportSignupRecordsDialog
        orgId={orgId}
        open={open}
        onOpenChange={setOpen}
      />
    </>
  );
}
