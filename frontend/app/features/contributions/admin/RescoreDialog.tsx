import { useState } from 'react';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { RadioGroup, RadioGroupItem } from '~/components/ui/radio-group';
import { calendarDateSchema } from '../schemas';

export interface RescoreChoice {
  apply_to_past: boolean;
  since: string | null;
}

export interface RescoreDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kindLabel: string;
  from: number;
  to: number;
  isReset: boolean;
  isPending: boolean;
  onConfirm: (choice: RescoreChoice) => Promise<void>;
}

type Scope = 'future' | 'past';

export function RescoreDialog({
  open,
  onOpenChange,
  kindLabel,
  from,
  to,
  isReset,
  isPending,
  onConfirm,
}: RescoreDialogProps) {
  const [scope, setScope] = useState<Scope>('future');
  const [since, setSince] = useState('');
  const applyPast = scope === 'past';
  const sinceInvalid = applyPast && since !== '' && !calendarDateSchema.safeParse(since).success;

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isReset ? `Reset ${kindLabel} to default?` : `Change ${kindLabel} points?`}
      description={`${kindLabel}: ${from} → ${to} points. Manual awards are never rescored.`}
      confirmLabel={isReset ? 'Reset' : 'Save'}
      isLoading={isPending}
      confirmDisabled={sinceInvalid}
      confirmTestId="rescore-confirm"
      cancelTestId="rescore-cancel"
      contentTestId="rescore-dialog"
      onConfirm={() =>
        onConfirm({ apply_to_past: applyPast, since: applyPast && since ? since : null })
      }
      bodyContent={
        <div className="flex flex-col gap-3">
          <RadioGroup
            value={scope}
            onValueChange={(value) => setScope(value as Scope)}
            className="flex flex-col gap-2"
          >
            <div className="flex items-center gap-2">
              <RadioGroupItem
                value="future"
                id="rescore-future-only"
                data-testid="rescore-future-only"
              />
              <Label htmlFor="rescore-future-only">Future only</Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem
                value="past"
                id="rescore-apply-past"
                data-testid="rescore-apply-past"
              />
              <Label htmlFor="rescore-apply-past">Apply to past entries</Label>
            </div>
          </RadioGroup>
          <div className="flex flex-col gap-1">
            <Label htmlFor="rescore-since-input" className="text-sm">
              Only entries since (optional, org timezone)
            </Label>
            <Input
              id="rescore-since-input"
              type="date"
              value={since}
              disabled={!applyPast}
              onChange={(e) => setSince(e.target.value)}
              data-testid="rescore-since-input"
            />
            {sinceInvalid && <p className="text-sm text-destructive">Pick a valid date</p>}
          </div>
        </div>
      }
    />
  );
}
