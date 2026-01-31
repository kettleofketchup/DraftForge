import { reactRouter } from '@react-router/dev/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

const ReactCompilerConfig = {
  // Compile all files in app/ directory
  sources: (filename: string) => filename.includes('/app/'),
};

export default defineConfig({
  plugins: [
    tailwindcss(),
    reactRouter({
      babel: {
        plugins: [['babel-plugin-react-compiler', ReactCompilerConfig]],
      },
    }),
    tsconfigPaths(),
  ],
  build: {
    rollupOptions: {
      onwarn(warning, warn) {
        // Suppress sourcemap warnings from "use client" directive transformation
        // These occur because React Router's Vite plugin transforms the directive
        // and loses sourcemap info. Verified harmless - no underlying errors hidden.
        if (warning.code === 'SOURCEMAP_ERROR') return;
        warn(warning);
      },
    },
  },
  server: {
    allowedHosts: ['localhost', 'dota.kettle.sh', 'nginx'],
    // Warm up frequently used files for faster initial loads
    warmup: {
      clientFiles: [
        './app/root.tsx',
        './app/routes/*.tsx',
        './app/components/**/*.tsx',
      ],
    },
  },
  optimizeDeps: {
    // Pre-bundle these dependencies for faster cold starts
    include: [
      // React core
      'react',
      'react-dom',
      'react-router',
      'react-router-dom',
      // Heavy UI libraries
      '@xyflow/react',
      'framer-motion',
      // Note: elkjs excluded - has optional web-worker dep that breaks optimization
      // Data/state management
      '@tanstack/react-query',
      '@tanstack/react-table',
      'zustand',
      'axios',
      // Form handling
      'react-hook-form',
      '@hookform/resolvers',
      'zod',
      // UI components (Radix)
      '@radix-ui/react-dialog',
      '@radix-ui/react-dropdown-menu',
      '@radix-ui/react-popover',
      '@radix-ui/react-select',
      '@radix-ui/react-tabs',
      '@radix-ui/react-tooltip',
      '@radix-ui/react-alert-dialog',
      '@radix-ui/react-avatar',
      '@radix-ui/react-collapsible',
      '@radix-ui/react-hover-card',
      '@radix-ui/react-label',
      '@radix-ui/react-progress',
      '@radix-ui/react-scroll-area',
      '@radix-ui/react-separator',
      '@radix-ui/react-slider',
      '@radix-ui/react-slot',
      '@radix-ui/react-toggle',
      '@radix-ui/react-toggle-group',
      // Icons (large bundles)
      'lucide-react',
      '@iconify/react',
      // Utilities
      'clsx',
      'tailwind-merge',
      'class-variance-authority',
      'date-fns',
      'sonner',
      'cmdk',
      '@headlessui/react',
      // Dota data
      'dotaconstants',
    ],
    // Force re-optimization when starting fresh
    force: process.env.VITE_FORCE_OPTIMIZE === 'true',
  },
});
