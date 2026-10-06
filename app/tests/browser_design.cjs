/* Run against isolated preview_design.py, never a production account.
   PLAYWRIGHT_MODULE can point to an existing Playwright installation.
   BROWSER_EXECUTABLE can select a locally installed Chrome binary. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const artifacts = process.env.DESIGN_ARTIFACTS || '/private/tmp/paperpulse-design-artifacts';
  await fs.mkdir(artifacts, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_EXECUTABLE,
  });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    page.setDefaultTimeout(8000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = 'http://127.0.0.1:8765';
    await page.goto(base + '/preview/login');
    // Reset only the isolated preview reader through real settings interactions.
    await page.goto(base + '/settings');
    while (await page.getByRole('button', { name: /^Remove / }).count()) {
      await page.getByRole('button', { name: /^Remove / }).first().click();
    }
    await page.locator('summary').click();
    for (const slug of ['cs.AI', 'cs.LG', 'stat.ML']) {
      await page.getByRole('searchbox', { name: 'Search categories' }).fill(slug);
      await page.locator('input[name="slugs"]').filter({ visible: true }).check();
    }
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.waitForURL(base + '/feed');
    await page.getByRole('heading', { name: 'Your feed', exact: true }).waitFor();
    await page.screenshot({ path: path.join(artifacts, 'feed-desktop.png'), fullPage: true });
    await context.route(base + '/assets/**', route => route.continue({
      url: route.request().url().replace(base + '/assets/', base + '/reference/assets/'),
    }));
    const reference = await context.newPage();
    await reference.goto(base + '/reference/');
    await reference.screenshot({ path: path.join(artifacts, 'blog-desktop.png'), fullPage: true });
    const metrics = async page => page.evaluate(() => {
      const result = {};
      for (const selector of ['body', '.site-header', '.site-title', '.site-sidebar',
        '.page-content .wrapper', '.site-footer', '.month-section h2', '.date-entry a']) {
        const element = document.querySelector(selector);
        const style = getComputedStyle(element);
        result[selector] = { fontFamily: style.fontFamily, fontSize: style.fontSize, fontWeight: style.fontWeight,
          lineHeight: style.lineHeight, color: style.color, padding: style.padding,
          width: style.width, marginBottom: style.marginBottom };
      }
      return result;
    });
    assert.deepEqual(await metrics(page), await metrics(reference), 'Blog/feed visual metrics match');
    await page.getByRole('link', { name: 'Oct 05, Mon' }).click();
    await page.getByRole('heading', { name: 'Your daily ArXiv summary' }).waitFor();
    assert.equal(await page.locator('time').getAttribute('datetime'), '2026-10-05');
    await page.getByText('No new papers today.', { exact: true }).waitFor();
    assert.equal(await page.locator('.post-content h2').filter({ hasText: 'Theme 1:' })
      .first().evaluate(el => getComputedStyle(el).borderBottomWidth), '0px');
    await page.screenshot({ path: path.join(artifacts, 'day-desktop.png'), fullPage: true });

    await page.getByRole('link', { name: 'Settings', exact: true }).click();
    await page.waitForLoadState('load');
    assert.equal(await page.locator('details').getAttribute('open'), null, 'Settings starts collapsed');
    await page.getByText('3 of 5 selected', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Remove Machine Learning (stat.ML)', exact: true }).click();
    assert.equal(await page.evaluate(() => document.activeElement.hasAttribute('data-remove')), true);
    await page.getByText('2 of 5 selected', { exact: true }).waitFor();
    await page.locator('summary').click();
    const search = page.getByRole('searchbox', { name: 'Search categories' });
    await search.fill('machine learning');
    assert.equal(await page.locator('.category-option:visible').count(), 2);
    await page.getByRole('combobox', { name: 'Subject' }).selectOption('stat');
    assert.equal(await page.locator('.category-option:visible').count(), 1);
    await page.getByRole('checkbox', { name: 'Machine Learning stat.ML', exact: true }).check();
    await page.getByRole('combobox', { name: 'Subject' }).selectOption('');
    await search.fill('cs.CL');
    await page.getByRole('checkbox', { name: 'Computation and Language cs.CL', exact: true }).check();
    await search.fill('cs.CV');
    await page.getByRole('checkbox', { name: 'Computer Vision and Pattern Recognition cs.CV', exact: true }).check();
    await page.getByText('5 of 5 selected', { exact: true }).waitFor();
    await search.fill('robotics');
    assert.equal(await page.getByRole('checkbox', { name: 'Robotics cs.RO', exact: true }).isDisabled(), true);
    await search.fill('no-such-category');
    await page.getByText('No categories match. Try another search or subject.', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(artifacts, 'picker-desktop.png'), fullPage: true });
    await search.press('Escape');
    assert.equal(await page.locator('details').getAttribute('open'), null);
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.waitForURL(base + '/feed');
    await page.getByRole('link', { name: 'Settings', exact: true }).click();
    await page.waitForLoadState('load');
    await page.getByText('5 of 5 selected', { exact: true }).waitFor();
    assert.equal(await page.locator('input[name="slugs"]:checked').count(), 5, 'Filtered selections saved');
    await page.screenshot({ path: path.join(artifacts, 'settings-desktop.png'), fullPage: true });

    await page.goto(base + '/onboarding');
    assert.notEqual(await page.locator('details').getAttribute('open'), null, 'Onboarding starts open');
    while (await page.getByRole('button', { name: /^Remove / }).count()) {
      await page.getByRole('button', { name: /^Remove / }).first().click();
    }
    assert.equal(await page.getByRole('button', { name: 'Save categories', exact: true }).isDisabled(), true);
    await search.fill('cs.LG');
    await page.getByRole('checkbox', { name: 'Machine Learning cs.LG', exact: true }).focus();
    await page.keyboard.press('Space');
    await page.getByText('1 of 5 selected', { exact: true }).waitFor();
    await search.fill('artificial');
    await page.getByRole('checkbox', { name: 'Artificial Intelligence cs.AI', exact: true }).check();
    await page.getByRole('button', { name: 'Save categories', exact: true }).click();
    await page.waitForURL(base + '/feed');
    await page.getByRole('link', { name: 'Settings', exact: true }).click();
    await page.waitForLoadState('load');
    await page.getByText('2 of 5 selected', { exact: true }).waitFor();

    for (const width of [390, 600, 768]) {
      await page.setViewportSize({ width, height: 844 });
      await reference.setViewportSize({ width, height: 844 });
      for (const route of ['/feed', '/feed/2026-10-05', '/settings', '/onboarding', '/login']) {
        await page.goto(base + route);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true,
          'No horizontal overflow at ' + width + ' on ' + route);
        await page.screenshot({ path: path.join(artifacts, route.replaceAll('/', '-').slice(1) + '-' + width + '.png'),
          fullPage: true });
      }
      await page.goto(base + '/feed');
      assert.deepEqual(await metrics(page), await metrics(reference), 'Responsive blog/feed metrics match at ' + width);
      if (width === 390) {
        await page.getByRole('checkbox', { name: 'Toggle navigation' }).focus();
        await page.keyboard.press('Space');
        await page.getByRole('link', { name: 'Settings', exact: true }).click();
        await page.waitForLoadState('load');
        await page.locator('summary').focus();
        await page.keyboard.press('Enter');
        assert.notEqual(await page.locator('details').getAttribute('open'), null);
        await page.getByRole('combobox', { name: 'Subject' }).selectOption('cs');
        const region = page.getByRole('region', { name: 'Category options' });
        assert.equal(await region.evaluate(el => el.scrollHeight > el.clientHeight), true);
        await region.focus();
        await page.keyboard.press('PageDown');
        await page.waitForFunction(() => document.querySelector('.picker-results').scrollTop > 0);
        await page.screenshot({ path: path.join(artifacts, 'picker-mobile.png'), fullPage: true });
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await context.clearCookies();
    await page.goto(base + '/login');
    await page.getByRole('link', { name: 'Continue with Google', exact: true }).waitFor();
    await page.screenshot({ path: path.join(artifacts, 'login-mobile.png'), fullPage: true });
    await page.goto(base + '/');
    await page.getByRole('link', { name: 'Sign in with Google', exact: true }).waitFor();
    // Force visited rendering in Chrome; JS color reads hide actual visited colors.
    await page.mouse.move(0, 0);
    const signIn = page.getByRole('link', { name: 'Sign in with Google', exact: true });
    const unvisitedButton = await signIn.screenshot();
    const devtools = await context.newCDPSession(page);
    await devtools.send('DOM.enable');
    await devtools.send('CSS.enable');
    const { root } = await devtools.send('DOM.getDocument');
    const { nodeId } = await devtools.send('DOM.querySelector', {
      nodeId: root.nodeId, selector: '.button-link',
    });
    await devtools.send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: ['visited'] });
    const visitedButton = await signIn.screenshot({ path: path.join(artifacts, 'visited-sign-in.png') });
    assert.equal(unvisitedButton.equals(visitedButton), true, 'Visited sign-in retains white text');
    const regressionStyle = await page.addStyleTag({ content: '.button-link:visited { color: #1756a9; }' });
    assert.equal(unvisitedButton.equals(await signIn.screenshot()), false,
      'Negative control detects the former dark visited text');
    await regressionStyle.evaluate(element => element.remove());
    await devtools.detach();
    const noJS = await browser.newContext({ javaScriptEnabled: false });
    const fallback = await noJS.newPage();
    await fallback.goto(base + '/preview/login');
    await fallback.goto(base + '/settings');
    assert.notEqual(await fallback.locator('details').getAttribute('open'), null);
    assert.equal(await fallback.locator('input[name="slugs"]').count(), 155);
    await fallback.getByRole('checkbox', { name: 'Artificial Intelligence cs.AI', exact: true }).uncheck();
    await fallback.getByRole('button', { name: 'Save changes', exact: true }).click();
    await fallback.waitForURL(base + '/feed');
    await fallback.goto(base + '/settings');
    assert.equal(await fallback.locator('input[name="slugs"]:checked').count(), 1);
    await noJS.close();
    assert.deepEqual(errors, [], 'No browser JavaScript errors');
    console.log('PASS: archive/day pages; picker search, subjects, limits, removal, persistence, both saves; '
      + 'keyboard/mobile scrolling; desktop/mobile blog metrics; visited sign-in text; JavaScript-disabled saving.');
    console.log('Screenshots: ' + artifacts);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
