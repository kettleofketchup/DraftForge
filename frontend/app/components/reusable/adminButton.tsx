import { UserLock } from 'lucide-react';
import { DestructiveButton, type DestructiveButtonProps } from '~/components/ui/buttons';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';

interface AdminOnlyButtonProps {
  buttonTxt?: string;
  tooltipTxt?: string;
  size?: DestructiveButtonProps['size'];
  className?: string;
  iconClassName?: string;
  onClick?: DestructiveButtonProps['onClick'];
  'data-testid'?: string;
}

export const AdminOnlyButton: React.FC<AdminOnlyButtonProps> = ({
  buttonTxt = 'Must be Admin',
  tooltipTxt = 'Be sure you are logged in. This request will fail if you are not a staff member or admin.',
  size,
  className,
  iconClassName = 'mr-2',
  onClick,
  'data-testid': dataTestId,
}) => {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <DestructiveButton
          size={size}
          className={className}
          onClick={onClick}
          data-testid={dataTestId}
        >
          <UserLock className={iconClassName} />
          {buttonTxt}
        </DestructiveButton>
      </TooltipTrigger>
      <TooltipContent className="bg-red-900 text-white rounded-lg">
        <div className="text-wrap text-center ">{tooltipTxt}</div>
      </TooltipContent>
    </Tooltip>
  );
};
