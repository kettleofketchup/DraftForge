import type { ToasterProps } from 'sonner';
import { Toaster as Sonner } from 'sonner';
import { brandBg } from '~/components/ui/buttons/styles';

const Toaster = ({ ...props }: ToasterProps) => {
  // App is always dark mode (see root.tsx), so hardcode dark theme
  return (
    <Sonner
      theme="dark"
      className="toaster group"
      toastOptions={{
        classNames: {
          // Sonner's theme="dark" applies inline background styles, so we need
          // !important (Tailwind !) to override them with our brand colors.
          toast: `!bg-background ${brandBg} text-white border-gray-600`,
          success: `!bg-green-950 ${brandBg} text-white border-gray-600`,
          warning: `!bg-red-950 ${brandBg} text-white border-gray-600`,
          closeButton: 'bg-red-900 text-white hover:bg-red-800 border-red-800',
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
