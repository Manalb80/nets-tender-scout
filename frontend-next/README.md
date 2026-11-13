# frontend-next: production React components

Components for the future Next.js production frontend of the Pre-Sales NETS
Enterprise Solution. Written in the Flowbite/Tailwind idiom with a dark
minimalist aesthetic, zero external CDN scripts, and env-driven configuration.

These do NOT run inside the claude.ai artifact. The artifact is a single-file
vanilla JS app with its own design tokens; loading the Tailwind CDN there would
apply Tailwind's preflight reset to every element and break all views. The
artifact keeps its own system; these components are its production twins.

## Stack assumptions
- Next.js 14+ (App Router), React 18, Tailwind CSS 3.4+
- Dark mode: `darkMode: "class"` in tailwind.config
- No Flowbite JS bundle required: interactivity is plain React state

## Environment
Copy to `.env.local`:

```
NEXT_PUBLIC_SHAREPOINT_BASE=https://netsinternational-my.sharepoint.com/personal/iqra_iqbal_nets-international_com/Documents/NETS-Karachi%20Presales-Technical%20Proposals
```

## CSS scoping contract (protects the legacy artifact)
Three locks, set in `tailwind.config.js` and `styles/globals.css`:
1. `corePlugins.preflight: false`: Tailwind's global reset is off. The reset is
   what breaks foreign pages, not the utilities.
2. `important: "#nets-next-root"`: every utility is emitted scoped, e.g.
   `#nets-next-root .p-6 {...}`. Loaded next to the legacy artifact, no rule
   can touch anything outside the wrapper.
3. A minimal hand-written reset lives under `.nets-next` in `styles/globals.css`.
   Dark mode is class-based (`.dark` on the wrapper), never media-query.

Every page must render inside `<div id="nets-next-root" className="nets-next">`.

## Components
- `components/RfpIntakeCard.jsx`: Step 1 RFP intake with upload, portal
  download link, SharePoint cloud folder path (truncated, copy with "Copied"
  feedback), and smart folder opening (base folder until the per-tender
  subfolder is provisioned and `sharepointConfirmed` is set).
- `components/ExecutiveDetailsDrawer.jsx`: leadership right-hand slide-out.
  Two tabs (Executive overview / RFP details), confirmed vs indicative source
  badges, exact-aware portal link, Esc/backdrop/X close, controlled via
  `open` + `onClose`. Exports `portalLink()` for reuse in tables.
- `components/KnowledgeBankBrowser.jsx`: read-only proposal library. Phrase
  search with highlights, vertical filter with counts, proposals/paragraphs
  modes, split list + reader with section jump. Pure props, no fetching.

Port order: Knowledge Bank page wiring, then Workbench, then role dashboards.
