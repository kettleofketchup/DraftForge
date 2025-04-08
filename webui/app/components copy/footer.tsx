import * as React from 'react';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';

import Container from '@mui/material/Container';
import Avatar from '@mui/material/Avatar';
import Button from '@mui/material/Button';


const pages = ['Tournaments', 'Dota', 'Blog'];
const settings = ['Profile', 'Account', 'Dashboard', 'Logout'];


import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import { styled } from '@mui/material/styles';



function Footer() {
  

  return (
<footer className=" sticky bottom-0 footer sm:footer-horizontal footer-center bg-base-300 text-base-content p-4">
  <aside>
    <p>Copyright © {new Date().getFullYear()} - DTX</p>
  </aside>
</footer>  );
}
export default Footer;