import * as TabsPrimitive from '@radix-ui/react-tabs';
import * as React from 'react';
import { useSearchParams } from 'react-router';

import { cn } from '~/lib/utils';

/**
 * Hook for syncing tab state with URL search params
 * @param paramName - The URL parameter name (default: "tab")
 * @param defaultValue - The default tab value
 * @returns [activeTab, setActiveTab] - Current tab and setter that updates URL
 */
function useUrlTabs(defaultValue: string, paramName = 'tab') {
  const [searchParams, setSearchParams] = useSearchParams();

  const activeTab = searchParams.get(paramName) || defaultValue;

  const setActiveTab = React.useCallback(
    (value: string) => {
      setSearchParams(
        (prev) => {
          const newParams = new URLSearchParams(prev);
          if (value === defaultValue) {
            newParams.delete(paramName);
          } else {
            newParams.set(paramName, value);
          }
          return newParams;
        },
        { replace: true },
      );
    },
    [setSearchParams, paramName, defaultValue],
  );

  return [activeTab, setActiveTab] as const;
}

function Tabs({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn('flex flex-col gap-2', className)}
      {...props}
    />
  );
}

function TabsList({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        'bg-transparent text-muted-foreground inline-flex min-h-11 w-fit items-center justify-center gap-2 p-1',
        className,
      )}
      {...props}
    />
  );
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        // Base styles. The explicit border and outline-none override the
        // app.css base `button` rule (#646cff hover border, webkit focus outline).
        'inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 py-2.5',
        'text-sm font-medium whitespace-nowrap cursor-pointer',
        'border border-transparent outline-none',
        'transition-all duration-150 ease-out',
        'shadow-sm',
        // Inactive state - primary tint, card border
        'data-[state=inactive]:bg-primary/15',
        'data-[state=inactive]:text-foreground',
        'data-[state=inactive]:border-border',
        // Hover (inactive only)
        'data-[state=inactive]:hover:bg-primary/25 data-[state=inactive]:hover:border-primary/40',
        'data-[state=inactive]:hover:shadow-md data-[state=inactive]:hover:-translate-y-0.5',
        // Active state - brand gradient
        'data-[state=active]:[background-image:var(--brand-gradient)]',
        'data-[state=active]:text-white',
        'data-[state=active]:shadow-brand-glow',
        'data-[state=active]:[text-shadow:_0_1px_2px_rgba(0,0,0,0.5)]',
        'data-[state=active]:-translate-y-0.5',
        // Focus styles
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        // Disabled
        'disabled:pointer-events-none disabled:opacity-50',
        // Icon styles
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn('flex-1 outline-none', className)}
      {...props}
    />
  );
}

export { Tabs, TabsContent, TabsList, TabsTrigger, useUrlTabs };
