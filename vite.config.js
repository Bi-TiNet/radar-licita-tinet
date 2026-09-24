import { defineConfig } from 'vite';

export default defineConfig({
  root: 'app/static',
  build: {
    outDir: '../../dist',
    emptyOutDir: true,
  },
});
