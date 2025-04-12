import { useState } from 'react'

import dtx from '../../assets/dtx.gif'
import Avatar from '@mui/material/Avatar';

import { Icon } from "@iconify/react";
import Popover from '@mui/material/Popover';
import Typography from '@mui/material/Typography';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Box from '@mui/material/Box';
import ResponsiveAppBar from '../../components/navbar';
import AppBar from '@mui/material/AppBar';
export function Welcome() {
  
  const [count, setCount] = useState(0)
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

      
      <div className="flex justify-center h-full content-center mb-0 mt-0 overflow-hidden p-0">
        <div className='justify-self-center content-center align-middle'>
          <a href="https://discord.gg/eXBZGjVp" 
            className=' justify-self-center content-center align-middle'
            target="_blank"
            aria-owns={open ? 'mouse-over-popover' : undefined}
            aria-haspopup="true"
            onMouseEnter={handlePopoverOpen}
            onMouseLeave={handlePopoverClose}>
            <div className="avatar flex ">
              <div className="ring-primary ring-offset-base-100  rounded-full ring ring-offset-2 w-100 shadow-xl hover:shadow-indigo-500/50
                              ]motion-safe:md:hover:animate-pulse motion-safe:md:hover:animate-spin motion-safe:transition delay-150 duration-300 easin-in-out">
                <img src={dtx} alt="Vite logo animate-spin w-36" />
              </div>
            </div>
          </a>
          <span className='flex justify-center pt-8 text-center w-full'>
            Click on the logo to join our Discord
          </span>

        </div>
    </div>

    </>
  )

}

