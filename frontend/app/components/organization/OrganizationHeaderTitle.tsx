import type { ReactNode } from 'react';

interface OrganizationHeaderTitleProps {
  name: string;
  action?: ReactNode;
}

export function OrganizationHeaderTitle({
  name,
  action,
}: OrganizationHeaderTitleProps) {
  return (
    <div
      data-testid="org-header-title"
      className="mb-2 flex flex-col items-start gap-2 sm:flex-row sm:justify-between sm:gap-0"
    >
      <h1 className="w-full min-w-0 text-3xl font-bold break-words sm:w-auto">
        {name}
      </h1>
      {action}
    </div>
  );
}
