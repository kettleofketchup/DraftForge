import type * as React from 'react';
import { TabsList, TabsTrigger } from '~/components/ui/tabs';
import { cn } from '~/lib/utils';

export interface FormTabItem {
  value: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
}

interface FormTabsListProps {
  tabs: FormTabItem[];
  /** Triggers get `${testIdPrefix}-tab-${value}`. */
  testIdPrefix: string;
  className?: string;
}

/** Tab strip for tabbed form dialogs: one scrollable compact row below sm, full width above. */
export function FormTabsList({
  tabs,
  testIdPrefix,
  className,
}: FormTabsListProps) {
  return (
    <TabsList
      className={cn(
        'w-full min-h-0 flex-nowrap justify-start overflow-x-auto [scrollbar-width:none] sm:min-h-11 sm:justify-center',
        className,
      )}
    >
      {tabs.map(({ value, label, icon: Icon }) => (
        <TabsTrigger
          key={value}
          value={value}
          className="min-h-8 flex-none px-3 py-1.5 sm:min-h-10 sm:flex-1 sm:px-4 sm:py-2.5"
          data-testid={`${testIdPrefix}-tab-${value}`}
        >
          {Icon && <Icon className="h-4 w-4" />}
          {label}
        </TabsTrigger>
      ))}
    </TabsList>
  );
}
