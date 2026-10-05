# Design Direction — F1 Intelligence Platform

## Design Intent

The product should feel like a fusion of:
- motorsport editorial;
- race-engineering instrumentation;
- premium automotive presentation;
- modern interactive data storytelling.

It must not look like:
- a generic admin dashboard;
- a crypto dashboard;
- a neon cyberpunk template;
- a collection of identical cards;
- an F1 broadcast clone.

The interface should feel original.

---

## Visual Personality

Keywords:
- precise;
- fast;
- technical;
- cinematic;
- restrained;
- premium;
- editorial;
- mechanical.

The visual hierarchy should communicate speed and engineering without turning every surface into decoration.

---

## Layout

Use:
- strong editorial headings;
- asymmetry where useful;
- generous negative space around hero moments;
- dense but disciplined telemetry layouts;
- full-width sections where charts/track visualizations need room;
- grid alignment throughout.

Avoid:
- card-inside-card-inside-card layouts;
- equal-weight sections;
- floating boxes for every metric;
- oversized empty dashboard chrome.

---

## Typography

Use a strong display face for:
- driver names;
- race names;
- major positions;
- section hero moments.

Use a highly readable sans-serif for:
- telemetry;
- tables;
- controls;
- labels;
- AI responses.

Telemetry values should use tabular numerals where supported.

Avoid making all text uppercase. Reserve uppercase for labels, session states, short metadata, and motorsport-style instrumentation.

---

## Color

Base palette:
- dark neutral / near-black surfaces;
- off-white text;
- controlled neutral borders;
- one primary interaction accent;
- restrained semantic colors for telemetry and status.

Do not assign colors to drivers solely for decoration if those colors reduce readability.

Green/red may be used carefully for faster/slower deltas, but never rely on color alone.

Avoid:
- rainbow gradients;
- excessive glow;
- large saturated backgrounds;
- glassmorphism across the whole UI.

---

## Motion

Motion should communicate:
- speed;
- hierarchy;
- state change;
- data progression.

Use:
- subtle page transitions;
- metric transitions;
- controlled track motion;
- scroll-linked hero effects;
- telemetry playback.

Avoid:
- constant ambient motion;
- excessive parallax;
- animation on every card;
- transitions that delay access to data.

Respect `prefers-reduced-motion`.

---

## 3D

3D is a feature, not the layout system.

Appropriate:
- homepage car/helmet hero;
- selected driver/team presentation;
- circuit model;
- telemetry lap replay;
- technical storytelling.

Not appropriate:
- every page background;
- navigation;
- forms;
- tables;
- standings;
- ordinary content cards.

3D scenes must:
- lazy-load;
- have static fallbacks;
- degrade gracefully on weaker devices;
- never block core data.

---

## Data Visualization

Telemetry must be readable before it is beautiful.

Charts should prioritize:
1. legibility;
2. alignment;
3. comparison;
4. interaction;
5. animation.

For lap comparison:
- synchronize traces;
- provide a clear time/distance axis;
- show selected driver states;
- expose tyre context;
- show delta separately from raw channels.

Do not use pseudo-precision beyond source quality.

---

## AI Surface

Pitwall should feel integrated into the product.

It may appear as:
- a persistent contextual entry point;
- an analysis panel;
- an inline explanation attached to telemetry/strategy.

Avoid a generic chat bubble that ignores page context.

The UI should make it clear when Pitwall is:
- retrieving data;
- calculating;
- interpreting.

---

## Responsive Design

Mobile:
- prioritize current race/session;
- stack metric groups;
- simplify charts without removing meaning;
- keep touch targets large;
- avoid horizontal page scrolling.

Desktop:
- allow telemetry and track visualization to use width;
- use multi-column comparison layouts;
- preserve strong editorial spacing.

---

## Accessibility

Required:
- semantic controls;
- keyboard navigation;
- focus states;
- non-color indicators;
- readable chart labels;
- text alternatives for meaningful imagery;
- reduced motion support;
- sufficient contrast.
