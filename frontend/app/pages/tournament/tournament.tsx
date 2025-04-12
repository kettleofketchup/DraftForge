import { useState } from 'react'

import Avatar from '@mui/material/Avatar';

import { Icon } from "@iconify/react";
import Popover from '@mui/material/Popover';
import Typography from '@mui/material/Typography';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Placeholder from '~/components/placeholder';
export function Tournament() {
  
  const [count, setCount] = useState(0)
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);



  return (
    <>
      <div className="flex justify-center h-full content-center mb-0 mt-0 overflow-hidden p-20">
        <div className='flex'>          
          <Placeholder/>
        </div>
      </div>
    </>
  )

}

