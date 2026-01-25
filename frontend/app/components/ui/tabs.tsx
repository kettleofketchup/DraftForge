import * as React from "react"
import * as TabsPrimitive from "@radix-ui/react-tabs"
import { useSearchParams } from "react-router"

import { cn } from "~/lib/utils"

/**
 * Hook for syncing tab state with URL search params
 * @param paramName - The URL parameter name (default: "tab")
 * @param defaultValue - The default tab value
 * @returns [activeTab, setActiveTab] - Current tab and setter that updates URL
 */
function useUrlTabs(defaultValue: string, paramName = "tab") {
  const [searchParams, setSearchParams] = useSearchParams()

  const activeTab = searchParams.get(paramName) || defaultValue

  const setActiveTab = React.useCallback((value: string) => {
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev)
      if (value === defaultValue) {
        newParams.delete(paramName)
      } else {
        newParams.set(paramName, value)
      }
      return newParams
    }, { replace: true })
  }, [setSearchParams, paramName, defaultValue])

  return [activeTab, setActiveTab] as const
}

function Tabs({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function TabsList({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "bg-transparent text-muted-foreground inline-flex min-h-11 w-fit items-center justify-center gap-2 p-1",
        className
      )}
      {...props}
    />
  )
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        // Base styles
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 py-2.5",
        "text-sm font-medium whitespace-nowrap cursor-pointer",
        "transition-all duration-150 ease-out",
        "shadow-sm",
        // Inactive state - lighter purple
        "data-[state=inactive]:bg-violet-800/50 dark:data-[state=inactive]:bg-violet-800/40",
        "data-[state=inactive]:text-violet-200 dark:data-[state=inactive]:text-violet-300",
        "data-[state=inactive]:border data-[state=inactive]:border-violet-600/50 dark:data-[state=inactive]:border-violet-600/40",
        // Hover - approaching primary (inactive only)
        "data-[state=inactive]:hover:bg-violet-700/60 dark:data-[state=inactive]:hover:bg-violet-700/50",
        "data-[state=inactive]:hover:text-violet-100 dark:data-[state=inactive]:hover:text-violet-200",
        "data-[state=inactive]:hover:border-violet-500 dark:data-[state=inactive]:hover:border-violet-500",
        "data-[state=inactive]:hover:shadow-md data-[state=inactive]:hover:-translate-y-0.5",
        // Active state - bright primary
        "data-[state=active]:bg-violet-500 dark:data-[state=active]:bg-violet-400",
        "data-[state=active]:text-white dark:data-[state=active]:text-violet-950",
        "data-[state=active]:border data-[state=active]:border-violet-400 dark:data-[state=active]:border-violet-300",
        "data-[state=active]:shadow-lg data-[state=active]:shadow-violet-500/50",
        "data-[state=active]:-translate-y-0.5",
        // Focus styles
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        // Disabled
        "disabled:pointer-events-none disabled:opacity-50",
        // Icon styles
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("flex-1 outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent, useUrlTabs }
