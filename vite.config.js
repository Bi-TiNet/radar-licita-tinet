import { defineConfig } from 'vite';

export default defineConfig({
  root: 'cloud',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
});
