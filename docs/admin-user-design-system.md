# RosaGo User → Admin design-system audit

## Source of truth

Audited the actual styles loaded by `templates/base.html` and
`templates/auth/login.html`, rather than sampling screenshots:

- `static/css/design-tokens.css`: shared brand, typography, surface, and shadow tokens.
- `templates/partials/fonts.html`: Inter 400/500/600/700/800 and Sora 600/700/800.
- `static/css/site.css`: public application typography, cards, controls, tables, badges, and spacing.
- `static/css/prototype-components.css`: unlayered navigation, dropdown, and brand refinements.
- `static/css/auth.css`: the current User login card, uppercase labels, Show/Hide,
  forgot-password pill, primary pill, secondary action, and footer.
- `static/css/theme.css`: shared root dark tokens and public/auth component overrides.
- `static/css/buttons.css`: compact secondary actions.

`site.css` imports the design tokens, prototype components, foundation refinements,
and buttons. Its foundation rules and later unlayered component overrides both
matter. For example, the final User login card uses 16px padding, not the earlier
30px declaration; the login submit button is a pill, not the earlier 10px radius.

## Actual User values

| Role | Light | Dark |
| --- | --- | --- |
| UI font | `--site-sans`: Inter, system-ui, -apple-system, Segoe UI, sans-serif | Same |
| Wordmark font | `--site-logo`: Sora, system-ui, sans-serif | Same |
| Red / links | `--site-red`: `#8E3B2C` | `#F0A28B` |
| Deep red / link hover | `--site-deep-red`: `#6E2A1E` | `#FFD2B7` |
| Filled primary | `--site-red`: `#8E3B2C` | `--theme-primary`: `#A74A37` |
| Filled primary hover | `--site-deep-red`: `#6E2A1E` | `--theme-primary-hover`: `#923E2E` |
| Gold | `--site-gold`: `#EEC35C` | Same |
| Application background | `--site-paper`: `#FFFDF8` | `#1D1714` |
| Card surface | White | `--site-surface`: `#2B221D` |
| Raised surface | White/tint, depending on component | `--site-raised`: `#362A23` |
| Tint | `--site-tint`: `#FDF6E3` | `#3B2D21` |
| Text | `--site-ink`: `#2E1A14` | `#F7EDDF` |
| Secondary text | `--site-muted`: `#6B5A48` | `#CBBBA7` |
| General border | `--site-border`: `#EFE2BD` | `#8B715A` |
| Card border | `#E3D3A3` (public/auth component declaration) | `--site-border` |
| Application control border | `#D8C694` | `--site-border` |
| Login control border | `--site-border` | `--site-border` |
| Logo Go accent | `#D6A21C` (public wordmark) | `--site-gold` |
| Focus | 3px red outline, usually 3px offset | 3px gold outline |

The shared light shadow is `0 1px 2px #6e2a1e0d, 0 8px 24px #6e2a1e0f`.
The shared dark shadow is `0 2px 16px #0004`; both come from `--site-shadow`.

Typography uses regular 400 body text, 500 navigation, 600 labels/actions/badges,
and 700–800 headings. Public body text is 17px/1.55; public page headings use
800 weight, approximately 28.8–38.4px, 1.1 line height, and negative tracking.
The User login uses a 25–32px/1.25 heading, 11px uppercase eyebrow with 2px
tracking, 12px uppercase labels, 14px description, and 16px inputs.

Component geometry and rhythm:

- Cards: 16px radius, 1.5px gold-neutral border, shared shadow; public padding
  24px or 18px on small screens. Login: 480px maximum width, 16px padding,
  3px red top accent.
- Fields: approximately 46px minimum height, 10px radius, 10–11px vertical and
  12–13px horizontal padding; labels have 6px separation. Login fields have
  18px bottom separation. Show/Hide is text, right-aligned inside the input.
- Application buttons: 44px minimum height, 10px radius, 600 weight; compact
  secondary actions also use 9px corners. Login primary: 48px minimum height,
  999px radius, 17px text, 20px arrow, and 18px gap.
- Navigation: 8px corners and warm gold selected surface with deep-red text.
  Dropdowns: 12px corners. Badges: 999px pills, 600 weight, tinted fill/border.
- Spacing commonly uses 6px label gaps, 8–12px inline gaps, 16px grids and field
  margins, 18px login field separation, and 24px page/section spacing.
- Links are red/deep red with underlines on ordinary text links; navigation and
  button-like links use clear hover surfaces and focus outlines.
- Dark fields use `--site-paper`; autofill uses the raised surface. Status
  success/error colors are semantic exceptions, not alternate brand palettes.

## Admin adoption and boundaries

`admin.css` aliases its semantic brand/surface/text/shadow tokens to `--site-*`
and the existing `--theme-*` values. Component-specific border/radius values
that the User styles do not expose as tokens are named Admin aliases, with
their source documented above. Published/draft/archived states remain semantic;
they do not determine general navigation or primary button colors.

Admin keeps its 260px sidebar, compact top bar, modular Dashboard grid, real
metrics/actions, permissions, and mobile disclosures. The warm sidebar uses
the User navigation's tinted selected surface and red/gold accents instead of
painting the entire administration workspace red. Operational typography stays
compact (14px body, 12–13px data/navigation, 16px module headings) using the same
families, weights, colors, tracking, and component proportions.

Login retains the existing arch image and User-derived form styling, native
required validation, autocomplete, CSRF, error states, Show/Hide, and theme
controls. User registration and social login are not introduced.

Admin never imports `site.css` or `auth.css` and does not use `.public-site`,
`.auth-site`, or `.registration-layout` selectors. Public templates/styles are
unchanged. Detailed Admin page content is outside this pass; its existing shared
buttons, fields, and surfaces inherit the common family without a page redesign.

## Verification

Use the existing Admin unittest suite, theme JavaScript tests, JS syntax check,
and `git diff --check`. Browser verification covers Login and Dashboard in light
and dark themes at 1366×768, 1440×900, tablet, and mobile widths; native required
fields; mouse/keyboard Show/Hide; primary button states; and no horizontal page
overflow. Login must fit the complete 1366×768 viewport without hiding content.
