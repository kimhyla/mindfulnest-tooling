import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

// Path C build target: a single self-contained storyboard_v59_prod.html that
// production_server.py serves via --storyboard <filename> (existing regex
// ^storyboard_v\d+.*\.html$ already accepts the new name; zero server-routing
// changes). The copy step lives in scripts/copy-to-event.sh.

export default defineConfig({
  plugins: [preact(), viteSingleFile()],
  build: {
    outDir: 'dist',
    cssCodeSplit: false,
    assetsInlineLimit: 100_000_000, // inline anything; we want one file
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});
