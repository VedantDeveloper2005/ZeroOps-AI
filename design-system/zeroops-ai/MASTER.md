# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** ZeroOps AI
**Generated:** 2026-07-27 18:14:09
**Category:** Developer tools SaaS
**Design Dials:** Variance 3/10 (Centered / Minimal) | Motion 2/10 (Subtle) | Density 7/10 (Standard)

---

## Global Rules

### Color Palette

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Primary | `hsl(215 86% 48%)` | `--color-primary` |
| On Primary | `#FFFFFF` | `--color-on-primary` |
| Accent | `hsl(226 70% 55%)` | `--color-accent` |
| Success | `hsl(156 72% 29%)` | `--color-success` |
| Background | `hsl(216 33% 97%)` | `--color-background` |
| Foreground | `hsl(222 47% 11%)` | `--color-foreground` |
| Muted surface | `hsl(216 30% 96%)` | `--color-surface-subtle` |
| Border | `hsl(214 26% 88%)` | `--color-border` |
| Destructive | `hsl(0 72% 46%)` | `--color-danger` |
| Focus ring | `hsl(215 86% 48%)` | `--color-primary` |

**Color Notes:** Blue communicates primary workspace actions; indigo is a restrained accent. Green, amber, and red are reserved for truthful status semantics. Dark-mode values are separately tuned in `src/app/globals.css`.

### Typography

- **Heading Font:** Geist Sans
- **Body Font:** Geist Sans
- **Data / code font:** Geist Mono
- **Mood:** restrained, operational, precise, trustworthy
- **Loading:** `next/font/google` in `src/app/layout.tsx`; no render-blocking CSS import

Use tabular figures for metrics, timestamps, versions, and cost values.

### Spacing Variables

*Density: 7/10 — Standard*

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.1)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | Hero images, featured cards |

---

## Component Specs

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: var(--primary);
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}

.btn-primary:hover {
  background: var(--primary-hover);
}

/* Secondary Button */
.btn-secondary {
  background: var(--card);
  color: var(--foreground);
  border: 1px solid var(--border);
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}
```

### Cards

```css
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-sm);
}

.card-interactive:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
```

### Inputs

```css
.input {
  padding: 12px 16px;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 200ms ease;
}

.input:focus {
  border-color: var(--primary);
  outline: none;
  box-shadow: 0 0 0 3px var(--primary-glow);
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.modal {
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Operational Minimalism

**Keywords:** restrained SaaS, dense operations, review-first, semantic status, truthful empty states

**Best For:** developer tooling, infrastructure operations, approval workflows, audit-heavy SaaS

**Key Effects:** quiet borders, compact cards, 8-12px radii, subtle elevation, blue focus and active states, limited 180-200ms motion

### Page Pattern

**Pattern Name:** Evidence -> Review -> Approval -> Execution

- **Workspace strategy:** Keep current project context visible across analysis, architecture, deployment, monitoring, security, activity, and settings.
- **Primary action:** One clear action per screen; review and approval actions outrank secondary utilities.
- **Data rule:** Never fabricate charts, incidents, savings, health, or telemetry. Prefer explicit empty, unavailable, permission, and disconnected states.

---

## Motion

Use 180-200ms color, opacity, and transform transitions. Route loading uses
`loading.tsx`, so shared layouts stay interactive while a destination renders.
Framer Motion is limited to feedback that benefits from presence transitions.
All motion must respect `prefers-reduced-motion`.

---

## Anti-Patterns (Do NOT Use)

- ❌ Decorative motion that competes with operational state
- ❌ Fabricated metrics, charts, health, savings, incidents, or activity
- ❌ Hidden horizontal navigation with no adaptive mobile control
- ❌ Glass, glow, or gradient effects used as default card styling

### Additional Forbidden Patterns

- ❌ **Emojis as icons** — Use SVG icons (Heroicons, Lucide, Simple Icons)
- ❌ **Missing cursor:pointer** — All clickable elements must have cursor:pointer
- ❌ **Layout-shifting hovers** — Avoid scale transforms that shift layout
- ❌ **Low contrast text** — Maintain 4.5:1 minimum contrast ratio
- ❌ **Instant state changes** — Always use transitions (150-300ms)
- ❌ **Invisible focus states** — Focus states must be visible for a11y

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [x] No emojis used as icons (use SVG instead)
- [x] All icons from consistent icon set (Heroicons/Lucide)
- [x] `cursor-pointer` on all clickable elements
- [x] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [x] Focus states visible for keyboard navigation
- [x] `prefers-reduced-motion` respected
- [x] Responsive: 375px, 768px, 1024px, 1440px
- [x] No content hidden behind fixed navbars
- [x] No horizontal scroll on mobile
