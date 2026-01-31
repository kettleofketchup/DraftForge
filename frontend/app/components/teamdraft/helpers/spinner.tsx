import { Loader2 } from 'lucide-react';
export const Spinner = () => {
  return (
    <div className="flex items-center justify-center">
      <Loader2 className="animate-spin" />
    </div>
  );
};
