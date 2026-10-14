# Personalized feed design

Status: implemented and verified locally on 2026-10-05; not deployed.
Approved by owner: 2026-10-05.

## Goal

Make every page in the personalized feed experience visually consistent with
the main PaperPulse blog. Replace the long arXiv category list with a compact,
searchable picker that makes selecting up to five categories easy.

The main blog is the visual reference. Scope includes the feed archive, daily
feed, onboarding, settings, and the shared app shell, including login pages.

## Approved choices

### Visual consistency

- Match the blog's header, sidebar, footer, content width, typography, link
  colors, spacing, and mobile navigation.
- Use the blog homepage's month headings and date-row styling in the feed archive.
- Use the blog article's title, date metadata, and research heading styles in
  daily feeds. Avoid adding category-divider styles to every research heading.
- Match form controls and buttons across onboarding and settings.

### Category picker

- Use a searchable checkbox picker in a collapsible, scrollable panel.
- Keep selected categories visible above the panel, with individual Remove
  buttons and a selection count such as “3 of 5 selected”.
- Label the panel trigger “Choose categories”. Open it by default during
  onboarding and collapse it by default in settings.
- Search by category name or code. Include an optional subject filter with
  readable names such as Computer Science, Mathematics, and Physics.
- Show readable category names with smaller category codes and checkboxes.
  Display roughly six to eight rows before scrolling.
- Keep the panel open when a category is selected. At five selections, explain
  the limit and keep deselection available.
- Reuse the same picker in onboarding and settings. Support keyboard use,
  mobile widths, and an explicit Save button.

## Progress

- [x] Review existing blog and app templates and styles.
- [x] Owner approves design direction.
- [x] Record goal, choices, and progress in shared repository docs.
- [x] Align shared app shell with the main blog.
- [x] Align feed archive month headings and date rows.
- [x] Align daily feed title, metadata, and content typography.
- [x] Build shared category picker and use it in onboarding and settings.
- [x] Align onboarding, settings, and login controls and spacing.
- [x] Verify desktop and mobile layouts against the blog.
- [x] Verify search, subject filtering, removal, selection limits, persistence
  across filtering, keyboard operation, and saving in both picker contexts.
- [x] Run relevant app tests and record results.
- [x] Review final changes and record any remaining issues.

## Evidence and handoff

Baseline before implementation: 29 API tests and 50 app tests passed on
2026-10-05. Implementation now uses shared picker markup/JavaScript, a snapshot
of the blog shell CSS, and matching archive/article markup. Browser verification
uses an isolated SQLite database, synthetic account, and synthetic category
content; production data and Google OAuth credentials are not used.

Update this checklist as work lands. Record validation results and any design
changes here so the next session can resume without relying on chat history.

## Verification results — 2026-10-05

- App suite: **50 passed**. Existing authentication, CSRF, category validation,
  account deletion, archive ordering, and safe Markdown rendering tests pass.
- Browser suite: **passed** in local Chrome using real signed app sessions and
  SQLite writes for a synthetic reader. No authentication override is added to
  the production app; the login helper exists only in the preview server.
- Compared rendered blog/feed font families, sizes, weights, line heights,
  colors, widths, padding, and margins at 1280, 768, 600, and 390 pixels.
  The local reference build's main and custom CSS match the current repo assets.
- Checked category name/code search, subject filtering, empty results, removable
  selections, empty/five-category limits, selections retained through filtering,
  settings/onboarding defaults, and persisted saves in both forms.
- Checked keyboard checkbox selection, panel opening/closing, removal focus,
  mobile menu navigation, and keyboard scrolling within bounded results.
- Checked archive/day/settings/onboarding layouts for horizontal overflow at
  phone and tablet widths; visually reviewed desktop and mobile screenshots.
- Checked anonymous login/landing pages and saving with JavaScript disabled.
  Browser reported no JavaScript errors. JavaScript-disabled pickers remain open
  with usable native checkboxes; search and subject filters require JavaScript.
- JavaScript syntax and whitespace checks pass for changed app files.
- No new runtime dependencies. No deployment, merge, or production data changes.
  Google OAuth round-trip was not retested; browser tests use isolated sessions.

Screenshots from this session: `/private/tmp/paperpulse-design-artifacts/`.
Key examples: `feed-desktop.png`, `day-desktop.png`, `settings-desktop.png`,
`picker-mobile.png`, `onboarding-390.png`, and `login-mobile.png`.

## Repeat browser checks

Start an isolated preview from the repo root:

```sh
PYTHONPATH=. app/.venv/bin/python app/tests/preview_design.py
```

Open `http://127.0.0.1:8765/preview/login` to sign in as the synthetic reader.
The preview binds only to loopback and stores its database/content in a temporary
folder. The blog reference uses the existing `blog/_site` build.

In another terminal, with Playwright available in the Node environment:

```sh
node app/tests/browser_design.cjs
```

Set `PLAYWRIGHT_MODULE` to an existing Playwright module path if needed;
`BROWSER_EXECUTABLE` can select an installed Chrome binary. Optional
`DESIGN_ARTIFACTS` controls the screenshot output directory. Browser tests
reset only the synthetic preview reader's categories using real form controls.

## Maintenance

`app/static/main.css` is the existing blog theme snapshot; `app/static/blog.css`
mirrors the blog's shell overrides. Update these snapshots alongside blog theme
changes. App-specific controls stay in `app/static/app.css`.

## Review fixes — 2026-10-05

- [x] Fix visited sign-in CTA colors with an explicit `.button-link:visited` rule.
- [x] Prevent static assets and favicon responses, including missing assets,
  from rewriting session cookies. Dynamic pages retain the existing session
  middleware, cookie settings, and CSRF checks.
- [x] Add deterministic overlapping-response tests using real signed sessions:
  hold an old asset response, obtain a new CSRF token, release the asset, and
  verify category saving still succeeds and persists in SQLite.
- [x] Verify regression tests fail with the original session middleware:
  all four cases reproduce HTTP 403. Fixed app suite: **54 passed**.
- [x] Remove browser suite's `networkidle` workaround. Updated local Chrome
  suite passes, including real saves and desktop/mobile checks.
- [x] Add visited-state screenshot regression: force Chrome's visited pseudo-state,
  verify button rendering stays identical, and verify an injected former dark
  text color changes the screenshot. Reviewed `visited-sign-in.png`.

These fixes are local and uncommitted; no production deployment performed.
