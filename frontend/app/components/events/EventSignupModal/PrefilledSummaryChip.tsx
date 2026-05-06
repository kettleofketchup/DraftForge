'use client';
import { useState, type ReactNode } from 'react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '~/components/ui/collapsible';
import { Badge } from '~/components/ui/badge';
import { Pencil } from 'lucide-react';
import { cn } from '~/lib/utils';

export type PrefilledSummaryChipProps = {
  testId: string;
  summary: string;
  children: ReactNode;
};

export function PrefilledSummaryChip({ testId, summary, children }: PrefilledSummaryChipProps) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        data-testid={testId}
        className={cn(
          'flex w-full items-center justify-between rounded-md border border-border',
          'bg-base-200 px-3 py-2 hover:bg-accent min-h-11',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        )}
      >
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{summary}</Badge>
          <span className="text-xs text-muted-foreground">from your profile</span>
        </div>
        <Pencil className="size-4 text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Edit</span>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-3">{children}</CollapsibleContent>
    </Collapsible>
  );
}
