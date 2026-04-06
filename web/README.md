# Web (Next.js + Tailwind + shadcn-style UI)

The repo ships a **Python** pipeline (FinBERT, CoinGecko, SQLite) with a **Next.js** app in this folder: **TypeScript**, **Tailwind CSS**, shadcn-style primitives under `src/components/ui`, and a FastAPI backend (`btc-paper-api`) proxied as `/api`.

## Theme (CSS variables)

`src/app/globals.css` defines your design tokens in `:root` and `.dark` (hex colors, `--radius`, sidebar/chart tokens). Tailwind maps them in `tailwind.config.ts` via `var(--token)` (this project uses **Tailwind v3**, so the Tailwind v4-only `@theme inline { ... }` block is **not** used here; the same mapping is done in the JS config).

Dark mode:

- `next-themes` adds `class="dark"` / `light` on `<html>` (see `src/app/layout.tsx`).
- There is also a `prefers-color-scheme: dark` fallback on `:root:not(.light)` so system dark works before hydration.

Fonts: **Geist Mono** is applied on `<body>` via the `geist` package.

## Default paths (shadcn convention)

| Item | Path |
|------|------|
| UI components | `src/components/ui` |
| Shared utils (`cn`) | `src/lib/utils.ts` |
| Global styles + CSS variables | `src/app/globals.css` |
| Tailwind config | `tailwind.config.ts` |

Why `components/ui` matters: the shadcn CLI and most community snippets assume imports like `@/components/ui/button`. Keeping that folder avoids broken imports and makes `npx shadcn@latest add …` drop files in the expected place (see `components.json`).

## Setup from scratch (if you recreate elsewhere)

```bash
npx create-next-app@latest --typescript --tailwind --eslint --app
cd your-app
npx shadcn@latest init
```

Then add components:

```bash
npx shadcn@latest add button
```

Install deps used by this hero (if not already):

```bash
npm install lucide-react @radix-ui/react-slot class-variance-authority framer-motion clsx tailwind-merge
```

## Run this folder

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:3000`.
