import { useState } from 'react';




import Placeholder from '~/components/placeholder';

export function About() {
  const [count, setCount] = useState(0);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  const handlePopoverOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };
  const handlePopoverClose = () => {
    setAnchorEl(null);
  };

  return (
    <>
      <div className="flex justify-center h-full content-center mb-0 mt-0 overflow-hidden p-20">
        <div className="flex">
          <Placeholder />
        </div>
      </div>
    </>
  );
}
