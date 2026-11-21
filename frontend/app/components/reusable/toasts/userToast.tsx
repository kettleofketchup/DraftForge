'use client';

import { UserRoundPlusIcon } from 'lucide-react';
import { toast } from 'sonner';
export const UserToast = (title: string) => {
  const toastTitle = () => {
    return (
      <div>
        <UserRoundPlusIcon className="mr-2 h-4 w-4 inline-block" />
        <span className="font-semibold">{title}</span>
      </div>
    );
  };
  toast(toastTitle(), {
    description: 'Sunday, December 03, 2023 at 9:00 AM',
  });
};
