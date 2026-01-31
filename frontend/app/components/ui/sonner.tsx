import type { ToasterProps } from 'sonner';
import { Toaster as Sonner } from 'sonner';

const Toaster = ({ ...props }: ToasterProps) => {
  // App is always dark mode (see root.tsx), so hardcode dark theme
  return (
    <Sonner
      theme="dark"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast: 'bg-gray-700 text-white border-gray-600',
          success: 'bg-green-950 text-white border-gray-600',
          warning: 'bg-red-950 text-white border-gray-600',
          closeButton: 'bg-red-900 text-white hover:bg-red-800 border-red-800',
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
