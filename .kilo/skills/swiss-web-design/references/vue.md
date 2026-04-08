# Vue / Nuxt — Swiss Design Patterns

## Component Libraries to Research

For Swiss-style Vue sites, search for these minimal/unstyled component options:

- **Radix Vue** — port of Radix primitives for Vue, unstyled and accessible
- **Headless UI** — unstyled, accessible components from the Tailwind team, works with Vue 3
- **Shadcn Vue** — community port of shadcn/ui for Vue. Good starting point, strip styling to Swiss minimalism

Avoid Vuetify, Element Plus, or Quasar for Swiss design — their Material/opinionated styling fights restraint.

## Recommended Stack Patterns

### Nuxt 3 + Tailwind (UnoCSS)
Nuxt's auto-imports and file-based routing reduce boilerplate, letting you focus on design. UnoCSS is also a good Tailwind alternative with a smaller footprint.

```
// nuxt.config.ts
modules: ['@nuxtjs/tailwindcss']
// or
modules: ['@unocss/nuxt']
```

Search: "Nuxt 3 Tailwind minimal template" for starting points.

### Nuxt 3 + Scoped Styles
Vue's `<style scoped>` is natural for component-level Swiss design tokens. Define global tokens in `assets/css/tokens.css` and import in `nuxt.config.ts`.

## Grid Implementation

Vue's template syntax works cleanly with CSS Grid:

```vue
<template>
  <div class="swiss-grid">
    <slot />
  </div>
</template>

<style scoped>
.swiss-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 24px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}
</style>
```

## Font Loading

Use `@nuxtjs/google-fonts` or `@nuxtjs/fontaine` for optimal font loading:

```
// nuxt.config.ts
modules: ['@nuxtjs/google-fonts'],
googleFonts: { families: { Inter: [400, 500, 700] } }
```

## Key Search Terms for Research

- "Nuxt 3 minimal landing page"
- "Vue 3 Swiss design components"
- "Headless UI Vue minimal theme"
- "Nuxt portfolio template clean"
- "UnoCSS minimal design system"
