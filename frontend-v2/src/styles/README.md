# Frontend styles

`main.ts` loads tokens, Tailwind, `index.css`, then Markdown styles.
`index.css` is the single entry for shared and page-level global styles.

| Owner | Responsibility |
| --- | --- |
| `tokens.css` | Semantic theme tokens and skins |
| `shared.css` | Document defaults, controls, forms and shared component primitives |
| `navigation.css` | Application header, bottom navigation and section workspace shell |
| `pages/<feature>.css` | The feature's global surfaces, layout, controls and responsive states |
| Feature/component styles | Locally owned details and scoped presentation |
| `markdown.css` | Rendered Markdown content |

Edit the owning stylesheet directly. Keep its mobile, desktop, light-mode and
interaction rules together. Do not add another late-imported patch sheet for an
existing page. Shared controls belong in shared styles; page-specific selectors
belong with that page. A new feature may have its own owner.

Content and management navigation follow the shared
[navigation layout contract](../../../docs/ENGINEERING_RULES.md#141-navigation-layout-contract).
`SectionWorkspaceShell` / `useSectionHeaderOffset` supply the visible header
offset and secondary navigation height. Sticky page menus consume these values
and add their own spacing; do not duplicate scroll tracking or hard-code a full
header height. Verify both navigation groups on desktop and phone, including
partial/full header hiding, return scrolling and breakpoint changes.

The play page's character and party disclosure buttons share one sizing rule in
`pages/play.css` and inherit the standard themed button appearance. Keep their
positioning separate without reintroducing different sizes or fixed colors.
Mobile edge controls also share their frame in `pages/play.css`: the left and
right controls mirror their rounded corners and omit the border at the screen edge.

Preserve selector specificity and overlapping media-query order when combining
rules. A declaration that looks redundant at one viewport may still be required
at another, or for an open drawer, loading/error state or plugin theme.

The old `styles.css` + `styles/v2.css` cascade and its historical patch sheets
have been retired. CSS class names containing `v2` are not version entry points.

For broad stylesheet changes, `e2e/style-consolidation.spec.ts` can compare the
previous global CSS against the same live DOM using `DICEFRAME_STYLE_REFERENCE`
(a private file with the previous CSS in its import order, without unresolved
imports). This avoids differences from random fixture IDs or asynchronous data.
The test also supports saved computed-style baselines: set
`DICEFRAME_STYLE_BASELINE` and `DICEFRAME_RECORD_STYLES=1` before editing, then
rerun without recording. Both cover 26 page entries on desktop/mobile in
dark/light themes. Keep recorded data and screenshots outside the repository.
Interaction journeys cover states that this resting-page comparison does not
exercise.
