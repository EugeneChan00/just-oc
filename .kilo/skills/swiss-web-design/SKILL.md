---
name: swiss-web-design
description: "Build websites and web UIs following Swiss/International Typographic Style design principles using modern frameworks (React, Vue, Svelte, SolidJS, etc.). Use this skill whenever the user wants a clean, minimal, timeless, or Swiss-style website, landing page, portfolio, or UI component. Also trigger when the user mentions: minimalist web design, grid-based layout, Helvetica-style typography, International Style, Bauhaus-inspired web, or asks for a design that 'won't look dated in 10 years.' If the user wants any website that prioritizes clarity and restraint over trendy visuals, this skill applies."
---

# Swiss Web Design

Build timeless, functional websites using Swiss/International Typographic Style principles with modern frontend frameworks.

## Why Swiss Design Works

Swiss design has stayed relevant since the 1950s because it focuses on the *essence* of communication rather than its *appearance*. Trendy designs with gradients, 3D effects, and complex animations age within 2-3 years. Swiss designs from decades ago still look contemporary because they rely on universal visual principles rather than fashionable techniques.

As Massimo Vignelli said: *"You can reach timelessness if you look for the essence of things and not the appearance."*

## The Five Pillars

Every design decision should trace back to one of these pillars:

### 1. Geometric Simple Shapes
Use circles, rectangles, and clean lines. If a shape isn't geometric, it should at least be simple. Complex illustrations, decorative elements, and ornamental graphics break the Swiss ethos. When you need visuals, prefer flat icons, simple SVGs, or high-contrast photography — never clip art or hyper-realistic renders.

### 2. Minimalist Typography
Typography is the backbone of Swiss design. Pick one — at most two — sans-serif typefaces and use them consistently. Good choices: Inter, Helvetica Neue, Suisse Intl, Aktiv Grotesk, or similar grotesque/neo-grotesque families. Let type hierarchy do the heavy lifting through size, weight, and spacing rather than decorative fonts.

- Headlines: large, bold, high contrast against the background
- Body: comfortable reading size (16-18px base), generous line-height (1.5-1.7)
- No more than 3-4 font sizes across the entire design
- Letter-spacing and text-transform are your friends for subtle hierarchy

### 3. Grid-Based Orderly Layouts
Every element should sit on a clear grid. This minimizes arbitrary alignment edges and creates visual rhythm. Use the framework's grid system or CSS Grid. Columns of 4, 8, or 12 work well. Asymmetric grids (like a 1/3 + 2/3 split) are distinctly Swiss when used intentionally.

- Align everything to the grid — no eyeballing
- Content blocks should have consistent gutters
- Use the grid to create visual relationships between elements

### 4. White Space as a Design Element
White space isn't empty — it's the visual rhythm of the design. Generous padding and margins create breathing room that makes content digestible. When in doubt, add more space. Swiss design uses white space *actively* to direct attention, not passively as leftover area.

- Section padding should feel generous (80-120px vertical on desktop)
- Don't crowd elements — let each piece of content stand on its own
- Negative space around key elements signals importance

### 5. Function First
Before any visual work, be crystal clear on the website's goal. Every element must serve the function. If an element doesn't directly support the user's task or the site's purpose, remove it. This sounds simple but requires deep understanding of the business/brand to execute well.

- Ask: "What is the one thing this page needs the visitor to do?"
- Every section should answer a question the visitor has
- Navigation should be obvious and minimal

## What to Avoid

These are the enemies of timeless design. They make sites look dated within a few years:

- **3D effects and skeuomorphism** — faux depth, realistic textures, bevels
- **Complex shadows** — subtle, single-direction shadows are okay; layered drop shadows are not
- **Complex gradients** — if you must use a gradient, keep it subtle (2 adjacent colors, low contrast)
- **Decorative animations** — motion should communicate state changes, not decorate
- **Excess graphic elements** — badges, ribbons, ornamental dividers, background patterns
- **Trendy visual styles** — glassmorphism, neumorphism, brutalism-for-its-own-sake

## Color

Swiss design uses color with restraint and purpose:

- Start with a near-white background and near-black text (not pure #000 / #fff)
- One accent color maximum, used sparingly for CTAs and interactive elements
- Photography can be full-color but should be high-quality and intentional
- Consider monochrome or duotone treatments for images to maintain cohesion

## Framework Implementation

This skill works with any modern component framework. When the user specifies a framework, read the corresponding reference file for framework-specific patterns:

| Framework | Reference |
|-----------|-----------|
| React / Next.js | Read `references/react.md` |
| Vue / Nuxt | Read `references/vue.md` |
| Svelte / SvelteKit | Read `references/svelte.md` |
| SolidJS / Other | Read `references/other-frameworks.md` |

If the user hasn't specified a framework, ask which one they prefer.

**General implementation rules regardless of framework:**

- Use the framework's component model to build reusable Swiss design primitives: `Container`, `Grid`, `Section`, `Heading`, `Text`
- CSS-in-JS, Tailwind, CSS Modules, or scoped styles are all fine — pick what the project uses
- Use CSS Grid or the framework's grid system for layout
- Define a design token system: spacing scale (4, 8, 16, 24, 32, 48, 64, 96, 128), font sizes, colors
- Responsive design is non-negotiable — Swiss grids adapt beautifully to mobile with fewer columns

## Examples and References

The `examples/` directory is a workspace for collecting reference material:

- **`examples/`** — Download or save reference website HTML/screenshots here for analysis
- **`examples/images/`** — Save design reference images, mood boards, or screenshots of Swiss design inspiration

When starting a new project, search online for Swiss web design references and save interesting examples to these folders. Looking at real examples helps calibrate the right level of minimalism — Swiss design is restrained, not empty.

Good search terms for finding references:
- "Swiss style web design examples"
- "International Typographic Style website"
- "minimalist grid-based web design"
- Pinterest: "Swiss web design"

## Design Checklist

Before delivering a design, verify against these questions:

- [ ] Can you name the one function this page serves?
- [ ] Are there only 1-2 typefaces, all sans-serif?
- [ ] Does every element sit on the grid?
- [ ] Is there generous white space between sections?
- [ ] Are all shapes geometric or simple?
- [ ] Would this design still look good in 10 years?
- [ ] Is there zero skeuomorphism, 3D, or complex gradients?
- [ ] Does the color palette use restraint (1 accent max)?
- [ ] Does every element serve the page's function?
