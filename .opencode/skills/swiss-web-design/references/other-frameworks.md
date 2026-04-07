# SolidJS, Astro, Qwik & Other Frameworks — Swiss Design Patterns

## SolidJS

SolidJS's fine-grained reactivity and small bundle size align with Swiss function-first philosophy.

- **Kobalte** — unstyled, accessible component primitives for Solid (like Radix)
- Use Tailwind or vanilla CSS — Solid supports both well
- Search: "SolidJS minimal template", "Kobalte custom theme"

## Astro

Astro's zero-JS-by-default and island architecture is arguably the most Swiss-aligned meta-framework — ship only what's needed.

- Use any UI component from React/Vue/Svelte inside Astro islands
- Astro's built-in scoped styles work perfectly for Swiss design tokens
- Search: "Astro minimal portfolio", "Astro landing page template clean"

## Qwik

Qwik's resumability means near-zero JS on page load — pure function-first.

- Search: "Qwik City minimal template", "Qwik Tailwind starter"

## General Principles for Any Framework

Regardless of framework, the Swiss design implementation follows the same pattern:

1. **Define design tokens first** — spacing scale (4px base), 1-2 sans-serif fonts, neutral palette + 1 accent
2. **Build grid primitives** — a `Container`, `Grid`, and `Section` component
3. **Build type primitives** — `Heading` (h1-h4) and `Text` components with constrained variants
4. **Compose pages from primitives** — no one-off styles, everything uses the design system

## CSS Framework Recommendations

| Approach | When to Use |
|----------|------------|
| Tailwind CSS | Most projects — fast, constrained by default |
| UnoCSS | When you want Tailwind-like DX with smaller output |
| Vanilla CSS + tokens | When the project prefers no CSS framework |
| Open Props | Pre-defined CSS custom properties, good Swiss starting point |

Search: "Open Props minimal design system" for a tokens-first approach.

## Key Search Terms

- "[framework name] minimal landing page template"
- "[framework name] Tailwind starter"
- "[framework name] design system tokens"
- "zero JS portfolio website"
