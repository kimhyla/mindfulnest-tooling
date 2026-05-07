import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { viteSingleFile } from 'vite-plugin-singlefile';
import { execSync } from 'node:child_process';

// Path C build target: a single self-contained storyboard_v59_prod.html that
// production_server.py serves via --storyboard <filename> (existing regex
// ^storyboard_v\d+.*\.html$ already accepts the new name; zero server-routing
// changes). The copy step lives in scripts/copy-to-event.sh.

// Per V59_CICD_GAP_FIX_SPEC_v1.md Phase A / LD DEPLOY_VERIFICATION_GATE_V1:
// Inject a <meta name="build-sha"> tag so the deploy script's post-deploy
// curl smoke can prove the served HTML matches the freshly built bundle.
// Without this, a stale server can serve old content silently after a deploy.
const resolveBuildSha = (): string => {
  if (process.env.BUILD_SHA) return process.env.BUILD_SHA.trim();
  try {
    return execSync('git rev-parse --short HEAD', {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    try {
      return execSync('git log -1 --pretty=%h', {
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'ignore'],
      }).trim();
    } catch {
      return 'unknown';
    }
  }
};

const buildSha = resolveBuildSha();

const injectBuildSha = {
  name: 'mn-inject-build-sha',
  enforce: 'post' as const,
  transformIndexHtml(html: string): string {
    const tag = `    <meta name="build-sha" content="${buildSha}">`;
    if (/<meta\s+name=["']build-sha["']/i.test(html)) {
      return html.replace(
        /<meta\s+name=["']build-sha["'][^>]*>/i,
        tag.trim(),
      );
    }
    if (/<head>/i.test(html)) {
      return html.replace(/<head>/i, `<head>\n${tag}`);
    }
    // Fallback: prepend to the document so the marker always lands in dist.
    return `${tag}\n${html}`;
  },
};

export default defineConfig({
  plugins: [preact(), viteSingleFile(), injectBuildSha],
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
