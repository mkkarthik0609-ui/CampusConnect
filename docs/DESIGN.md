# CampusConnect design language

A rebuild of the SPA UI modelled on the **interaction design, layout and components** of ellipsus.com
(scroll choreography, section rhythm, header, footer, annotations). Ellipsus' own fonts and colours are
NOT used: CampusConnect has its own near-black / near-white palette and type.

## Tokens (already in `frontend/src/index.css` - use the semantic Tailwind names, never raw hex)
- Light: paper `#f7f7f5` (`bg-background`), ink `#0b0b0c` (`text-foreground`). Dark: `#0a0a0b` / `#f2f2f0`.
  Light and dark are inversions; every component must look right in both (`.dark` class on `<html>`).
- Primary action = ink on paper (black button on light, near-white button on dark). One champagne accent
  (`text-saffron`, `bg-saffron-soft`) for "needs attention" only. Status colours stay semantic (ok/warn/danger).
- Headings/titles/numerals: `font-display` = **Poppins** (the logo wordmark face), weights 300-500, tight
  tracking (-0.03em), large sizes. Body: **Outfit** (`font-sans`). IDs: JetBrains Mono.
- Logo: `components/app/BrandMark.jsx` (`<Brand/>`, `<BrandMark/>`), a thin-stroke vector using `currentColor`.
  Used in the header, footer, loaders, error pages, favicon, social card.
- Radii 8px controls / 12-24px surfaces, hairline borders (`border-border`), almost no shadows in light.

## Ellipsus patterns to reproduce (what to study, in `https://ellipsus.com/`)
1. **Sticky light header**: wordmark left; nav items with chevron dropdown mega-menus (Features / Library /
   About style), plain links, right-aligned outlined "Log in" + solid "Sign up" buttons. Header condenses and
   gets a hairline on scroll; collapses to a sheet menu on mobile.
2. **Hero** (full viewport, dark band): huge light display headline, floating drifting "dust" particles and
   hand-drawn cursor/arrow glyphs that parallax with pointer + scroll. For us: a three.js scene (the
   interlocking-hooks logo as a 3D tube/ring, particles, pointer parallax, scroll-driven rotation).
3. **Scroll-scrubbed text reveal**: a pinned big headline whose words go from dim to full contrast as you
   scroll (GSAP ScrollTrigger scrub), sections alternate near-black / near-white.
4. **Showcase**: pinned section with three uppercase small-caps feature labels; scroll progress switches the
   active label and the product mock (chat / meetings / classes) beside it.
5. **Statement section** with hand-drawn SVG annotations: underline/circle strokes drawn on scroll
   (stroke-dashoffset), arrow callouts with small handwritten-style captions, line-art illustration that
   parallaxes at the bottom.
6. **Counter** band: big numbers that count up when scrolled into view.
7. **Sign-up banner**: dark scene, line-art illustration, one pill CTA.
8. **Footer**: black, giant quote with a blinking caret (typewriter), left column of UPPERCASE small links,
   social/icon row, legal links row, address. Different footers for different areas (landing = giant
   reveal footer; auth = minimal ticker; app = slim status-bar footer).
9. Micro-interactions: link underline wipes, buttons with arrow nudge, cards that lift, smooth anchor scroll.

## Motion rules
- Three.js (`three`) and GSAP (`gsap` + `gsap/ScrollTrigger`) only. Lazy-load three via dynamic `import()`;
  cap DPR at 2, pause rendering when off-screen / tab hidden, dispose geometries/materials/renderer on unmount.
- Respect `prefers-reduced-motion`: no scrubbing/parallax/particles, render static final states.
- No WebGL support -> graceful static fallback (inline SVG logo). Never block first paint on 3D.
- The CSP is `script-src 'self'`: no inline scripts, no CDN scripts; fonts are bundled (fontsource).
- Animations must not cause layout shift; use transform/opacity.

## Loading, errors, SEO
- Page loader = the logo mark drawing itself (stroke-dashoffset), then fading. Route-level `Suspense`.
- Skeleton loaders (`components/app/skeletons.jsx`) mirror the real layout of each data view; never spinners
  alone. Skeleton shimmer respects reduced motion.
- Custom error pages (404, 403, 500, offline, route error boundary) share `ErrorPageLayout`, with the logo,
  a large display code, helpful actions.
- SEO: per-route `<title>`/description/canonical/OG/Twitter via `useMeta`, JSON-LD, `robots.txt`,
  `sitemap.xml`, `manifest.webmanifest`, OG image, `noindex` on authenticated routes.
