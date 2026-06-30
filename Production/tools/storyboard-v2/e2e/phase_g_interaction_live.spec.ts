/**
 * PHASE_G_LIVE_INTERACTION_V1 — live Event_4 operator-path proof (RC11).
 * Requires :5114 with watercolors seeded and fresh build-sha.
 *
 * Playwright dragTo does not populate custom dataTransfer (application/x-mn-drag).
 * DROP-WC-LIVE-1 tries dragTo first, then falls back to live HTML5 drop on the
 * capture-bound waveform — same DOM path as operator drag after dragstart.
 */
import { test, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test';

const LIVE = process.env.STORYBOARD_LIVE_BASE_URL ?? 'http://127.0.0.1:5114';
const LIVE_EVENT = 'Event_4';

async function serverReachable(request: APIRequestContext): Promise<boolean> {
  try {
    const res = await request.get(`${LIVE}/api/event/current`, { timeout: 5000 });
    return res.ok();
  } catch {
    return false;
  }
}

/** Pick a watercolor key not already rendered as a cue block on the waveform. */
async function pickUnusedWatercolorKey(
  request: APIRequestContext,
  page: Page,
  waveform: Locator,
): Promise<string> {
  const wcBody = await (await request.get(`${LIVE}/api/phase/watercolor_list`)).json();
  const keys = ((wcBody.items ?? []) as Array<{ key?: string }>)
    .map((it) => String(it.key ?? '').trim())
    .filter(Boolean);
  expect(keys.length).toBeGreaterThan(0);
  const cueTitles = await waveform.locator('.mn-waveform-cue-block').evaluateAll((els) =>
    els.map((el) => el.getAttribute('title') ?? ''),
  );
  const used = new Set<string>();
  for (const title of cueTitles) {
    const m = title.match(/^([^ @]+)/);
    if (m?.[1]) used.add(m[1].toLowerCase());
  }
  for (const key of keys) {
    if (!used.has(key.toLowerCase())) return key;
  }
  return keys[keys.length - 1]!;
}

/** Live HTML5 drop on capture-bound waveform (DROP-CAPTURE-1 on production bundle). */
async function liveHtml5WatercolorDrop(
  page: Page,
  tile: Locator,
  waveform: Locator,
  key: string,
): Promise<void> {
  const tileBox = await tile.boundingBox();
  const wfBox = await waveform.boundingBox();
  expect(tileBox).not.toBeNull();
  expect(wfBox).not.toBeNull();
  await page.evaluate(
    ({ key, tileX, tileY, dropX, dropY }) => {
      const dt = new DataTransfer();
      const payload = JSON.stringify({
        kind: 'lib-watercolor',
        lib_key: key,
        animation_type: 'fade_in',
      });
      dt.setData('application/x-mn-drag', payload);
      dt.setData('text/plain', payload);
      const dragStart = {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: tileX,
        clientY: tileY,
      };
      const dropEvt = {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: dropX,
        clientY: dropY,
      };
      const tileEl = document.querySelector(`[data-testid="phase-b-watercolor-tile-${key}"]`);
      if (tileEl) tileEl.dispatchEvent(new DragEvent('dragstart', dragStart));
      const wf = document.querySelector(
        '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-timeline"]',
      );
      if (!wf) throw new Error('waveform missing');
      wf.dispatchEvent(new DragEvent('dragenter', dropEvt));
      wf.dispatchEvent(new DragEvent('dragover', dropEvt));
      wf.dispatchEvent(new DragEvent('drop', dropEvt));
    },
    {
      key,
      tileX: tileBox!.x + tileBox!.width / 2,
      tileY: tileBox!.y + tileBox!.height / 2,
      dropX: wfBox!.x + wfBox!.width * 0.5,
      dropY: wfBox!.y + wfBox!.height * 0.5,
    },
  );
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ request }) => {
  test.skip(!(await serverReachable(request)), `Live server unreachable at ${LIVE}`);
  const cur = await request.get(`${LIVE}/api/event/current`);
  const body = await cur.json();
  expect(body.event_id).toBe(LIVE_EVENT);
  const wc = await request.get(`${LIVE}/api/phase/watercolor_list`);
  expect(wc.ok()).toBeTruthy();
  const wcBody = await wc.json();
  expect((wcBody.count ?? 0) as number).toBeGreaterThan(0);
});

test('LIB-WC-LIVE-1 — library watercolors filter shows server rows', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}&tab=phase_b`);
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible({ timeout: 60_000 });
  await page.selectOption('[data-testid="library-tier-select"]', 'watercolors');
  await expect(page.locator('[data-testid="library-loading"]')).toBeHidden({ timeout: 30_000 });
  await expect(page.locator('[data-testid="library-empty-tier"]')).toBeHidden({ timeout: 30_000 });
  const countText = await page.locator('[data-testid="library-count"]').innerText();
  const m = countText.match(/(\d+)\s*\/\s*(\d+)/);
  expect(m).not.toBeNull();
  expect(Number(m![1])).toBeGreaterThan(0);
  expect(Number(m![2])).toBeGreaterThan(0);
});

test('DROP-WC-LIVE-1 — watercolor tile → cue on live waveform', async ({ page, request }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}&tab=phase_b`);
  await expect(page.locator('[data-testid="phase-producer-b"]')).toBeVisible({ timeout: 60_000 });

  const waveform = page.locator(
    '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-timeline"]',
  );
  await expect(waveform).toBeVisible({ timeout: 30_000 });
  await expect.poll(async () => {
    const v = await waveform.getAttribute('data-loaded-duration-ms');
    return v ? Number(v) : 0;
  }, { timeout: 60_000 }).toBeGreaterThan(0);
  await expect(waveform).toHaveAttribute('data-drop-capture-bound', 'WAVEFORM_DROP_CAPTURE_V1');

  const dropKey = await pickUnusedWatercolorKey(request, page, waveform);
  const tile = page.locator(`[data-testid="phase-b-watercolor-tile-${dropKey}"]`);
  await expect(tile).toBeVisible({ timeout: 30_000 });
  const imgDraggable = await tile.locator('img').evaluate((el) => (el as HTMLImageElement).draggable);
  expect(imgDraggable).toBe(false);

  const cueBefore = Number((await waveform.getAttribute('data-cue-count')) ?? '0');

  await tile.dragTo(waveform, {
    targetPosition: { x: 0.5, y: 0.5 },
    force: true,
  });
  let cueAfter = Number((await waveform.getAttribute('data-cue-count')) ?? '0');
  if (cueAfter <= cueBefore) {
    await liveHtml5WatercolorDrop(page, tile, waveform, dropKey);
    cueAfter = Number((await waveform.getAttribute('data-cue-count')) ?? '0');
  }

  expect(cueAfter).toBeGreaterThan(cueBefore);
  await expect(
    waveform.locator(`.mn-waveform-cue-block[title*="${dropKey}"]`).first(),
  ).toBeVisible({ timeout: 15_000 });
});
