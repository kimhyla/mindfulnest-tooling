/**
 * Single Playwright e2e server origin — must match playwright.config.ts webServer port.
 * Import SERVER here (or from helpers.ts) instead of hardcoding localhost:5111/5200.
 */
export const SERVER = process.env.STORYBOARD_BASE_URL ?? 'http://localhost:5200';
