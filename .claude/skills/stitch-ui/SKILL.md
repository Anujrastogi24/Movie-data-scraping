---
name: stitch-ui
description: Convert a Google Stitch / Figma UI design into a Django template for this MovieCinema project. Use when the user provides a Stitch HTML/CSS export, a Figma design, or a screenshot/image of a UI and wants it turned into a working page or component. Output must match the project's existing plain-CSS conventions (design tokens, Poppins, boxicons, Swiper) — NOT Tailwind.
---

# Stitch / Figma → MovieCinema UI

Turn a Stitch (or Figma) design into a Django template that drops into this project
cleanly. Stitch exports **Tailwind** markup; this project uses **plain CSS with design
tokens**. Your job is to translate, not to paste.

## Project conventions (must follow)

- **Templates** live in `MovieCinema/home/templates/` (e.g. `index.html`, `movie.html`).
- **Styles** go in `MovieCinema/static/css/style.css` (plain CSS, ~950 lines). Add new
  rules here; do not introduce Tailwind, a build step, or a second stylesheet.
- **Static refs** use Django tags: `{% load static %}` at the top, then
  `<link rel="stylesheet" href="{% static 'css/style.css' %}">` and
  `src="{% static 'js/...' %}"`. Never hard-code `/static/...` paths.
- **Icons**: [boxicons](https://boxicons.com) — `<i class='bx bx-home'></i>`. Reuse
  these instead of inline SVGs from Stitch where an equivalent exists.
- **Carousels/sliders**: the project already loads Swiper
  (`swiper-bundle.min.css` / `.min.js`). Reuse Swiper markup rather than custom JS.
- **Fonts**: Poppins is imported at the top of `style.css`. Don't re-import fonts.

## Design tokens — map ALL colors to these

Defined in `:root` in `style.css`. Map the Stitch palette onto them; only add a new
token if nothing fits.

| Token              | Value                  | Use for                     |
|--------------------|------------------------|-----------------------------|
| `--main-color`     | `#ffb43a` (amber)      | accents, buttons, highlights|
| `--hover-color`    | `hsl(37, 94%, 57%)`    | hover states                |
| `--body-color`     | `#1e1e2a` (dark navy)  | page background             |
| `--container-color`| `#2d2e37`              | cards, panels, surfaces     |
| `--text-color`     | `#fcfeff` (near-white) | body text                   |

Reference them as `var(--main-color)`, etc. Replace any hex Stitch emits with the
closest token.

## Workflow

1. **Read the input.**
   - *HTML/CSS export*: read the markup. Identify structure (header, sections, cards,
     grid) and the Tailwind classes in play.
   - *Screenshot/image*: View it. Describe the layout to yourself — sections, spacing,
     hierarchy, components — before writing any code.

2. **Check for reuse first.** Look at existing templates (`index.html`, `movie.html`,
   `user.html`, etc.) and `style.css`. If the design has a header/nav/search/card that
   already exists, reuse that markup and class names instead of inventing new ones.

3. **Translate Tailwind → plain CSS.**
   - Convert utility classes (`flex gap-4 px-6 bg-...`) into semantic class names
     (`.movie-card`, `.hero`, `.detail-grid`) with corresponding rules in `style.css`.
   - Use `rem` units and the existing spacing feel. Keep it responsive with the same
     media-query style already in `style.css`.
   - Strip Stitch's CDN `<script src="...tailwind...">` and any `font-family` resets —
     the project already handles those.

4. **Build the template.**
   - New full page → new file in `MovieCinema/home/templates/`, starting with
     `{% load static %}` and the standard `<head>` (copy from `index.html`).
   - Component/partial → integrate into the relevant existing template.
   - Use `{% static %}` for every asset and `{% url '...' %}` for links/forms
     (mirror the existing `searchdata` form in `index.html`).

5. **Wire it up (only if a new page).** Add a view in `MovieCinema/home/views.py` and a
   route in `MovieCinema/home/urls.py`. Ask the user for the URL path and view name if
   not obvious. Don't wire routing for a pure component.

6. **Verify.** Confirm the CSS additions don't collide with existing class names, that
   all colors use tokens, and that it renders. Offer to run the app
   (`python manage.py runserver`) so the user can see it.

## Guardrails

- Do **not** add Tailwind, npm, or any build tooling — this is a plain Django + CSS app.
- Do **not** create a new CSS file; extend `style.css`.
- Do **not** invent backend data — use placeholder content or wire to existing
  context variables, and tell the user which template context the page expects.
- Keep new class names scoped and descriptive to avoid clobbering the ~950 lines of
  existing styles.
- Preserve accessibility: real `alt` text, semantic tags (`<header> <nav> <main>`),
  labelled form inputs.

## Quick reference — page skeleton

```html
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="{% static 'css/style.css' %}">
    <link rel="stylesheet" href="{% static 'css/swiper-bundle.min.css' %}">
    <link href='https://unpkg.com/boxicons@2.1.1/css/boxicons.min.css' rel='stylesheet'>
    <title>MovieCinema</title>
</head>
<body>
    <!-- translated design here -->
    <script src="{% static 'js/swiper-bundle.min.js' %}"></script>
    <script src="{% static 'js/main.js' %}"></script>
</body>
</html>
```
