# Svelte / SvelteKit — Swiss Design Patterns

## Component Libraries to Research

Svelte's component model naturally lends itself to Swiss design — minimal abstractions, scoped styles by default:

- **Bits UI** — headless component primitives for Svelte (like Radix for Svelte)
- **Shadcn Svelte** — port of shadcn/ui for Svelte, built on Bits UI + Tailwind
- **Skeleton UI** — Svelte UI toolkit. More opinionated, but can be themed minimally

For maximum Swiss control, consider building primitives from scratch — Svelte's component overhead is tiny.

## Recommended Stack Patterns

### SvelteKit + Tailwind
The lightest stack for Swiss design. SvelteKit's zero-JS-by-default philosophy aligns with function-first design.

```
// Install: npx svelte-add@latest tailwindcss
```

Search: "SvelteKit Tailwind minimal starter" for clean starting points.

### SvelteKit + Scoped CSS
Svelte's `<style>` block is scoped by default — perfect for Swiss component isolation. Define global tokens in `app.css`:

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;
  --font-sans: 'Inter', system-ui, sans-serif;
  --color-text: #1a1a1a;
  --color-bg: #fafafa;
  --color-accent: #0055ff;
}
```

## Grid Implementation

```svelte
<div class="grid">
  <slot />
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: var(--space-6);
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 var(--space-6);
  }
</style>
```

## Font Loading

Use `@fontsource/inter` for self-hosted fonts (no external requests):

```
npm install @fontsource/inter
// In +layout.svelte:
import '@fontsource/inter/400.css'
import '@fontsource/inter/700.css'
```

## Key Search Terms for Research

- "SvelteKit minimal landing page"
- "Svelte Swiss design"
- "Bits UI custom theme"
- "SvelteKit portfolio template minimal"
- "Svelte CSS Grid layout patterns"
