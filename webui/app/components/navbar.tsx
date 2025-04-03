import * as React from 'react';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import IconButton from '@mui/material/IconButton';
import Typography from '@mui/material/Typography';
import Menu from '@mui/material/Menu';
import MenuIcon from '@mui/icons-material/Menu';
import Container from '@mui/material/Container';
import Avatar from '@mui/material/Avatar';
import Button from '@mui/material/Button';
import Tooltip from '@mui/material/Tooltip';
import MenuItem from '@mui/material/MenuItem';
import AdbIcon from '@mui/icons-material/Adb';
import dtx from '../assets/dtx.gif'

const pages = ['Tournaments', 'Dota', 'Blog'];
const settings = ['Profile', 'Account', 'Dashboard', 'Logout'];


import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import { styled } from '@mui/material/styles';



function ResponsiveAppBar() {
  const [anchorElNav, setAnchorElNav] = React.useState<null | HTMLElement>(null);
  const [anchorElUser, setAnchorElUser] = React.useState<null | HTMLElement>(null);

  const handleOpenNavMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorElNav(event.currentTarget);
  };
  const handleOpenUserMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorElUser(event.currentTarget);
  };

  const handleCloseNavMenu = () => {
    setAnchorElNav(null);
  };

  const handleCloseUserMenu = () => {
    setAnchorElUser(null);
  };

  return (
    <Box sx={{ flexGrow: 1, alignContent: "left" }}>

    <AppBar position="fixed" sx={{backgroundColor: "#1e3d6f"}} >
      <Container maxWidth="xs" sx={{flexGrow:1}}>
        <Toolbar disableGutters >
            
            
          
       
          <Box sx={{ flexGrow: 5, alignContent: "start", display: { xs: 'none', md: 'flex' } }}>
            <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={{ xs: 1, sm: 2, md: 12, xl: 16 }}
                >
                <Button 
                    href={"/tournament"}
                    sx={{ my: 2, color: 'white', display: 'block' }}
                >
                    Dota
                </Button>

                <Button 
                    href={"/tournament"}
                    sx={{ my: 2, color: 'white', display: 'block' }}
                >
                    Tournament
                </Button>
                <Button
                    href={"/blog"}
                    sx={{ my: 2, color: 'white', display: 'block' }}
                >
                    Blog
                </Button>
            </Stack>

          </Box>
          

        </Toolbar>
      </Container>
    </AppBar>
    </Box>
  );
}
export default ResponsiveAppBar;