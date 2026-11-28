import * as React from 'react';

export interface EventFormNavigation {
  navigateToField: (field: string) => void;
}

const EventFormNavigationContext =
  React.createContext<EventFormNavigation | null>(null);

export const EventFormNavigationProvider = EventFormNavigationContext.Provider;

/** Null outside an event settings dialog. */
export function useEventFormNavigation(): EventFormNavigation | null {
  return React.useContext(EventFormNavigationContext);
}
