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

## Components
- `components/RfpIntakeCard.jsx`: Step 1 RFP intake with upload, portal
  download link, SharePoint cloud folder path (truncated, copy with "Copied"
  feedback), and smart folder opening (base folder until the per-tender
  subfolder is provisioned and `sharepointConfirmed` is set).

More components are ported one view at a time per the production migration
plan (Knowledge Bank first, then Workbench, then role dashboards).
