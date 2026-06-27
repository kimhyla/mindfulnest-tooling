// SCOPE_CLIENT_AUTHORITY_V1 — URL authority + build-sha drift contract.
//
// Dedicated-port sync (5110+N ↔ Event_N) is covered by unit tests +
// verify_scope_client_authority_durability.sh against live Event_2 server.
// This e2e pins client behavior on the e2e fixture: URL ?event= is authoritative
// and build-sha drift sets data-build-sha-drift on body.

import { test, expect } from '@playwright/test';

const FIXTURE_EVENT = 'Event_e2e_fixture';

test.describe('SCOPE_CLIENT_AUTHORITY_V1 — URL authority + build-sha drift', () => {
  test('?event= fixture resolves scope chip even when port implies Event_1', async ({ page }) => {
    await page.goto(`/?event=${FIXTURE_EVENT}`);

    await expect(page.locator('body')).toHaveAttribute(
      'data-resolved-scope',
      new RegExp(`${FIXTURE_EVENT}:global:v\\d+`),
      { timeout: 15_000 },
    );
  });

  test('build-sha drift sets body marker when live HTML differs from bundled meta', async ({
    page,
  }) => {
    await page.route('**/*', async (route) => {
      const url = route.request().url();
      if (
        route.request().resourceType() === 'document'
        || (url.includes('localhost') && !url.includes('/api/') && route.request().method() === 'GET')
      ) {
        const response = await route.fetch();
        let body = await response.text();
        if (body.includes('name="build-sha"')) {
          body = body.replace(
            /(<meta\s+name=["']build-sha["']\s+content=["'])[^"']+(["'])/i,
            '$1drift-test-sha$2',
          );
        }
        await route.fulfill({
          status: response.status(),
          headers: response.headers(),
          body,
        });
        return;
      }
      await route.continue();
    });

    await page.goto(`/?event=${FIXTURE_EVENT}`);
    await expect(page.locator('body')).toHaveAttribute('data-resolved-scope', /.*/, {
      timeout: 15_000,
    });

    // Trigger ServerRehydrateWatcher poll / visibility path via reload without cache bust on meta
    await page.evaluate(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await expect(page.locator('body')).toHaveAttribute(
      'data-build-sha-drift',
      /.+/,
      { timeout: 20_000 },
    );
  });
});
