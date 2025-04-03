import { useState } from 'react'

import dtx from '../assets/dtx.gif'
import Avatar from '@mui/material/Avatar';

import { Icon } from "@iconify/react";
import Popover from '@mui/material/Popover';
import Typography from '@mui/material/Typography';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Box from '@mui/material/Box';
import ResponsiveAppBar from '../components/navbar';
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
    <Box sx={{ height: "100%", width:"100%" }}>



        <a href="https://react.dev" 
          className='animate-bounce'
          target="_blank"
          aria-owns={open ? 'mouse-over-popover' : undefined}
          aria-haspopup="true"
          onMouseEnter={handlePopoverOpen}
          onMouseLeave={handlePopoverClose}>
          <Avatar  className="logo " >
            <img src={dtx} alt="Vite logo animate-spin" />
          </Avatar>
        </a>
        

      <div className="card">
     
       
      </div>
      <p className="read-the-docs">
      Click on the logo to join our Discord
      </p>
      <Popover
        id="mouse-over-popover"
        sx={{ pointerEvents: 'none' }}
        open={open}
        anchorEl={anchorEl}
        anchorOrigin={{
          vertical: 'top',
          horizontal: 'center',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'left',
        }}
        onClose={handlePopoverClose}
        disableRestoreFocus
      >
        <Typography sx={{ p: 1 }}>Join Now.</Typography>
      </Popover>

    </Box>
    </>
  )

}

