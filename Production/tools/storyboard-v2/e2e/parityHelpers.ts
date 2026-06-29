/** Shared helpers for behavioral-parity + touchpoint-a parity tests. */
import { expect, type Page, type Route } from '@playwright/test';

export async function mockSnapshot(page: Page): Promise<void> {
  await page.route('**/api/state/snapshot', async (r) => {
    await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  });
}

export async function synthDrop(
  page: Page,
  selector: string,
  payload: Record<string, unknown>,
): Promise<void> {
  const el = page.locator(selector);
  await expect(el).toBeVisible();
  const box = await el.boundingBox();
  if (!box) throw new Error(`No bounding box for ${selector}`);
  const x = box.x + box.width * 0.5;
  const y = box.y + box.height * 0.5;
  await el.evaluate(
    (node: Element, args: { payloadStr: string; clientX: number; clientY: number }) => {
      const dt = new DataTransfer();
      dt.setData('application/x-mn-drag', args.payloadStr);
      dt.setData('text/plain', args.payloadStr);
      const drop = new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: args.clientX,
        clientY: args.clientY,
      });
      node.dispatchEvent(drop);
    },
    { payloadStr: JSON.stringify(payload), clientX: x, clientY: y },
  );
}

export async function mockStoryboardIntroState(page: Page): Promise<void> {
  await page.route('**/api/v2/event/**/state', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        _module_version: 1,
        videos: {
          intro: {
            video_role: 'intro',
            beats: {
              beat_01: { speaker: 'Tessa', text: 'Fixture line one.', phase_1: { options: [{}, {}, {}], selected_option: 1 } },
              beat_02: { speaker: 'Tessa', text: 'Fixture line two.' },
              beat_03: { speaker: 'Chipper', text: 'Fixture line three.' },
            },
            display_order: ['beat_01', 'beat_02', 'beat_03'],
          },
        },
      }),
    });
  });
}
