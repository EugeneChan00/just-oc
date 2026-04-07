# React / Next.js — Swiss Design Patterns

## Component Libraries to Research

When building Swiss-style React sites, search online for these to find clean, minimal component options:

- **Radix UI Primitives** — unstyled, accessible primitives you can style from scratch (ideal for Swiss design since you control every visual detail)
- **Shadcn/ui** — copy-paste components built on Radix + Tailwind. Good starting point, then strip back the styling to Swiss minimalism
- **React Aria** (Adobe) — accessibility hooks without visual opinions

Avoid heavy-styled libraries like Material UI or Ant Design — their visual language fights against Swiss restraint.

## Recommended Stack Patterns

### Next.js + Tailwind
Best for most Swiss design projects. Tailwind's utility classes map directly to Swiss design tokens:

```
spacing: 4px grid (p-1 = 4px, p-2 = 8px, p-4 = 16px ...)
typography: font-sans with Inter or similar grotesque
colors: neutral palette + single accent
```

Search: "Tailwind CSS Swiss design config" for community presets.

### Next.js + CSS Modules
For projects that prefer scoped CSS over utilities. Define a global `tokens.css` with CSS custom properties for the spacing scale, colors, and type sizes.

### Styled Components / Emotion
Works well with a theme provider that defines Swiss design tokens. Create a `theme.ts` with the spacing scale, font stack, and color palette.

## Grid Implementation

```jsx
// CSS Grid is the most Swiss-aligned layout tool
// Use a 12-column grid with consistent gutters
<div style={{
  display: 'grid',
  gridTemplateColumns: 'repeat(12, 1fr)',
  gap: '24px',
  maxWidth: '1200px',
  margin: '0 auto',
  padding: '0 24px'
}}>
```

Search online for "CSS Grid Swiss design layout" and "asymmetric grid React component" for more complex Swiss grid patterns.

## Font Loading

For Swiss typography, self-host fonts via `next/font` for optimal loading:

```jsx
import { Inter } from 'next/font/google'
const inter = Inter({ subsets: ['latin'] })
```

Search for: "Inter font", "Helvetica Neue web font", "Suisse Intl webfont" for typeface options.

## Key Search Terms for Research

When building, search online for these to find current patterns and examples:

- "Next.js minimal landing page template"
- "React Swiss design component library"  
- "Tailwind minimal design system"
- "Radix UI custom theme minimal"
- "Next.js portfolio template clean minimal"
