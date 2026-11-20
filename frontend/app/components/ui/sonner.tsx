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
          toast: `!bg-background ${brandBg} text-white border-base-50`,
          success: `!bg-success-surface ${brandBg} text-white border-base-50`,
          warning: `!bg-warning-surface ${brandBg} text-white border-base-50`,
          closeButton:
            'bg-destructive/50 text-white hover:bg-destructive/60 border-destructive/60',
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
