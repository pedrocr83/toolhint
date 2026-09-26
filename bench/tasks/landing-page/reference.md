Judge the page from its HTML and CSS. `reference/index.html` is one acceptable answer, not the only one.

- **Distinctive, not generic (weigh this most):**
  - a clear visual idea that fits a warehouse-routing product, not a stock SaaS template (centered hero, three identical cards, purple gradient, Inter everywhere);
  - deliberate typography, with a characterful display face paired with a readable body face;
  - a considered colour system, defined as tokens;
  - layout with some tension or rhythm;
  - restrained, purposeful motion.
- **Everything asked for:** hero, features, pricing and FAQ in one `index.html` with inline CSS; believable, specific copy about route optimization for warehouse pickers.
- **Responsive:** works from a 360px phone up without horizontal scrolling. Grids collapse, and type scales with `clamp()` or media queries.
- **Accessible:**
  - semantic landmarks (`header`, `nav`, `main`, `footer`) and one `h1` with an ordered heading outline;
  - visible `:focus-visible` styles, and `prefers-reduced-motion` honoured;
  - sufficient colour contrast, and alt text or `aria-hidden` on decoration;
  - an FAQ that works with the keyboard (`details`/`summary` or buttons with `aria-expanded`), and pricing that reads well in a screen reader.
- **Craft:** valid, tidy markup; no dead links pretending to be buttons; no lorem ipsum.

Deduct for: a generic template look, missing sections, broken mobile layout, missing focus styles, low contrast, or placeholder copy.
