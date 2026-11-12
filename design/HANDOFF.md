# Hasanet Portal UI: Savanna (light) + Nightwatch (dark)

> **For Claude Code.** Re-skin the Hasanet ISP portal frontend (React + Tailwind, consuming the Django 5 / DRF API). There is **one layout and two themes**: **Savanna** for light mode and **Nightwatch** for dark mode. Switching the theme changes only CSS variables and never the layout or markup.
>
> - `renders/light/*.png` and `renders/dark/*.png` show the visual target for every screen in both modes.
> - `reference-html/{light,dark}/*.html` are static mockups. Read them for exact spacing, sizes and colours, then build real reusable React components. Don't paste the HTML in.

## 1. Screens

| Screen | Light | Dark | Audience |
|---|---|---|---|
| Admin dashboard | `renders/light/dashboard.png` | `renders/dark/dashboard.png` | Operator / NOC |
| Subscribers list | `renders/light/subscribers.png` | `renders/dark/subscribers.png` | Operator / support |
| Customer self-care | `renders/light/selfcare.png` | `renders/dark/selfcare.png` | Subscribers |
| Hotspot captive portal (390px) | `renders/light/captive.png` | `renders/dark/captive.png` | Walk-up hotspot users |

All figures are sample data. Wire them to the real endpoints. The Paybill `123456` is a placeholder.

## 2. Theme mechanics (do this first)
1. Put the variables below in `src/styles/theme.css`. Light values go under `:root`, and dark values go under `.dark`.
2. In Tailwind, set `darkMode: 'class'` and map every colour to a variable, for example `bg: 'var(--bg)'`. Components then use **semantic classes only** (`bg-surface text-text border-border`). Don't use hard-coded hex values, and don't use `dark:` variants for colours.
3. Build a `ThemeProvider` with three modes: `light`, `dark` and `system`, defaulting to `system` through `prefers-color-scheme`. Store the choice in `localStorage` (`hasanet-theme`) and toggle the `dark` class on `<html>`. Add an inline script in `index.html` that applies the class before first paint to avoid a flash.
4. Put a `ThemeToggle` (sun/moon segmented pill, shown in the admin top bar) in both admin and customer headers. On the captive portal, always follow the system setting and show no toggle.
5. Fonts swap with the theme:
   - **Light:** `Plus Jakarta Sans` for everything, with 800 weight for titles.
   - **Dark:** `Inter` for body text, `Space Grotesk` for headings and `JetBrains Mono` for numbers, codes and IPs.

   Expose `--font`, `--head-font` and `--num-font`. Self-host them with `npm i @fontsource/plus-jakarta-sans @fontsource/inter @fontsource/space-grotesk @fontsource/jetbrains-mono` and don't use a CDN.
6. Shape tokens also differ by theme:
   - **Light:** cards 20px, controls fully rounded (999px).
   - **Dark:** cards 12px, controls 8px.

   Expose them as `--radius` and `--btn-r`.
7. In dark mode, card titles are UPPERCASE with 0.12em tracking at 12.5px. Handle this with a `.dark .card-title` rule, not with separate markup.

## 3. Tokens

| Token | Light: Savanna | Dark: Nightwatch |
|---|---|---|
| `--bg` | `#F4F1EA` | `#070B14` |
| `--surface` | `#FFFFFF` | `#0D1424` |
| `--surface2` | `#FBF9F4` | `#111A2E` |
| `--border` | `#E9E3D6` | `#1A2540` |
| `--border-soft` | `#F1ECE2` | `#141E34` |
| `--border-strong` | `#E0D8C7` | `#22304F` |
| `--text` | `#14231B` | `#E6EDF7` |
| `--muted` | `#5E6B62` | `#8A9AB8` |
| `--faint` | `#8F978F` | `#5B6B8A` |
| `--primary` | `#0B4D33` | `#22D3EE` |
| `--on-primary` | `#fff` | `#04131A` |
| `--accent` | `#F2772E` | `#A3E635` |
| `--ok` | `#15803D` | `#4ADE80` |
| `--ok-bg` | `#E7F6EC` | `rgba(74,222,128,.10)` |
| `--warn` | `#C2410C` | `#FBBF24` |
| `--warn-bg` | `#FFF1E6` | `rgba(251,191,36,.10)` |
| `--bad` | `#B91C1C` | `#F87171` |
| `--bad-bg` | `#FDECEC` | `rgba(248,113,113,.10)` |
| `--chip` | `#F1ECE2` | `#16213A` |
| `--input-bg` | `#fff` | `#0A1120` |
| `--rail` | `#0B4D33` | `#060A12` |
| `--rail-fg` | `rgba(255,255,255,.6)` | `#5B6B8A` |
| `--rail-active-bg` | `rgba(255,255,255,.14)` | `rgba(34,211,238,.12)` |
| `--rail-active-fg` | `#FFFFFF` | `#22D3EE` |
| `--rail-active-bar` | `#F2772E` | `#22D3EE` |
| `--hero` | `#0B4D33` | `#0A1222` |
| `--hero-fg` | `#FFFFFF` | `#E6EDF7` |
| `--hero-accent` | `#9BE3A8` | `#22D3EE` |
| `--highlight` | `#F2772E` | `#22D3EE` |
| `--highlight-fg` | `#FFFFFF` | `#04131A` |
| `--mpesa` | `#3BB54A` | `#3BB54A` |
| `--chart-1` | `#0B4D33` | `#22D3EE` |
| `--chart-2` | `#3BB54A` | `#A3E635` |
| `--chart-3` | `#F2772E` | `#818CF8` |
| `--chart-4` | `#F6C343` | `#F472B6` |
| `--chart-muted` | `#D8EBDD` | `#1E2B47` |
| `--radius` | `20px` | `12px` |
| `--btn-r` | `999px` | `8px` |
| `--shadow` | `0 1px 0 rgba(20,35,27,.04),0 8px 24px -12px rgba(20,35,27,.12)` | `none` |

```css
:root {
  --bg: #F4F1EA;
  --surface: #FFFFFF;
  --surface2: #FBF9F4;
  --border: #E9E3D6;
  --border-soft: #F1ECE2;
  --border-strong: #E0D8C7;
  --text: #14231B;
  --muted: #5E6B62;
  --faint: #8F978F;
  --primary: #0B4D33;
  --on-primary: #fff;
  --accent: #F2772E;
  --ok: #15803D;
  --ok-bg: #E7F6EC;
  --warn: #C2410C;
  --warn-bg: #FFF1E6;
  --bad: #B91C1C;
  --bad-bg: #FDECEC;
  --chip: #F1ECE2;
  --input-bg: #fff;
  --rail: #0B4D33;
  --rail-fg: rgba(255,255,255,.6);
  --rail-active-bg: rgba(255,255,255,.14);
  --rail-active-fg: #FFFFFF;
  --rail-active-bar: #F2772E;
  --hero: #0B4D33;
  --hero-fg: #FFFFFF;
  --hero-accent: #9BE3A8;
  --highlight: #F2772E;
  --highlight-fg: #FFFFFF;
  --mpesa: #3BB54A;
  --chart-1: #0B4D33;
  --chart-2: #3BB54A;
  --chart-3: #F2772E;
  --chart-4: #F6C343;
  --chart-muted: #D8EBDD;
  --radius: 20px; --btn-r: 999px;
  --font: 'Plus Jakarta Sans', sans-serif; --head-font: var(--font); --num-font: var(--font);
}
.dark {
  --bg: #070B14;
  --surface: #0D1424;
  --surface2: #111A2E;
  --border: #1A2540;
  --border-soft: #141E34;
  --border-strong: #22304F;
  --text: #E6EDF7;
  --muted: #8A9AB8;
  --faint: #5B6B8A;
  --primary: #22D3EE;
  --on-primary: #04131A;
  --accent: #A3E635;
  --ok: #4ADE80;
  --ok-bg: rgba(74,222,128,.10);
  --warn: #FBBF24;
  --warn-bg: rgba(251,191,36,.10);
  --bad: #F87171;
  --bad-bg: rgba(248,113,113,.10);
  --chip: #16213A;
  --input-bg: #0A1120;
  --rail: #060A12;
  --rail-fg: #5B6B8A;
  --rail-active-bg: rgba(34,211,238,.12);
  --rail-active-fg: #22D3EE;
  --rail-active-bar: #22D3EE;
  --hero: #0A1222;
  --hero-fg: #E6EDF7;
  --hero-accent: #22D3EE;
  --highlight: #22D3EE;
  --highlight-fg: #04131A;
  --mpesa: #3BB54A;
  --chart-1: #22D3EE;
  --chart-2: #A3E635;
  --chart-3: #818CF8;
  --chart-4: #F472B6;
  --chart-muted: #1E2B47;
  --radius: 12px; --btn-r: 8px;
  --font: Inter, sans-serif; --head-font: 'Space Grotesk', sans-serif; --num-font: 'JetBrains Mono', monospace;
}
```

## 4. Shared layouts (identical in both themes)
- **Admin shell:** a 72px icon rail on the left (`--rail`, which is forest green in light and near-black in dark). The active item uses `--rail-active-bg` and a 3px inset left bar in `--rail-active-bar` (orange in light, cyan in dark). The 64px top bar has the brand, a system-status pill, ⌘K search, the EAT clock, ThemeToggle, notifications and an avatar. The rail collapses to a drawer below 1024px.
- **Dashboard:** greeting header with Export and **New subscriber**. Below that:
  - Four KPI cards. The first uses the `highlight` variant: a solid orange card in light, cyan-outlined in dark.
  - Collections area chart (2/3 width) beside a plan-mix donut (1/3).
  - A row of three: M-Pesa payments feed, sites and core health, alerts.
- **Subscribers:** five site-health cards, then a table card with count tabs, search and Site/Plan filters, row checkboxes, a dark bulk-action bar (Send STK reminder / Renew / Reset PPPoE) and pagination. Signal colour: above −60 dBm is ok, −60 to −67 is warn, below −67 is bad.
- **Customer self-care:** a top nav and a full-width **hero band** (`--hero`) with "Habari, {name}" and "N days left on your plan". Cards overlap the band by about 110px. The grid is 2fr / 1fr:
  - **Left:** plan card, data-usage bars, then connection details and recent payments.
  - **Right:** M-Pesa pay card, help card (`--highlight` background in light), upgrade offers.
- **Captive portal:** a hero band with rounded bottom corners, then an overlapping package-picker card (radio cards with a MOST POPULAR tag), a +254 phone field, a full-width green **Pay KES X** M-Pesa button, voucher entry and a help line. Keep it under 60 KB of JS, with no chart library, and make it work inside the MikroTik walled garden.

## 5. Components
`ThemeProvider`, `ThemeToggle`, `Card`/`CardHeader`, `KpiCard` (with `highlight`), `StatusBadge` (ok/warn/bad/neutral), `Button` (primary / secondary / ghost / mpesa), `Input`, `SegmentedControl`, `AreaChart`/`BarChart`/`DonutChart`/`Sparkline` (Recharts, with colours read from `--chart-*` variables so they switch with the theme), `PaymentsFeedRow`, `SiteHealthRow`, `AlertRow`, `DataTable` + `BulkActionBar`, `MpesaPayCard` (with pending/success/failed STK states), `PackagePicker`, `MpesaBadge`. Use `lucide-react` icons with stroke 1.8.

## 6. Rules
- Format money as `KES 2,500` with `Intl.NumberFormat('en-KE')` and tabular numerals.
- Mask MSISDNs in admin lists, e.g. `0722 ••• 418`.
- Show all times in Africa/Nairobi.
- Meet WCAG AA in **both** themes. Show focus rings in `--primary`, and give icon buttons an `aria-label`.
- Use skeleton loaders shaped like the cards. Give each empty state a one-line hint and an action.
- Fetch data with React Query, kept separate from presentational components.

## 7. Order of work
1. Theme tokens, ThemeProvider and toggle, fonts.
2. Primitives.
3. Admin shell and dashboard.
4. Subscribers.
5. Self-care.
6. Captive portal (lightweight route/bundle).
7. API wiring.
8. Responsive and accessibility pass.

**After each screen:** screenshot it at 1440px in **both** modes and compare against `renders/light` and `renders/dark`.
