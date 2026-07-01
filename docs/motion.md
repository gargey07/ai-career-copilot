# Motion

Full rules live in [design-system.md](./design-system.md#7-motion). Quick reference:

| Duration | Use |
| --- | --- |
| 150ms | Micro-interactions (hover, press) |
| 250ms | Element enter (fade-in / slide-up) |
| 400ms | Page-level transitions |

Easing: `ease-out` for enters, `ease-in-out` for loops. Keep `fade-in` and `slide-up`
keyframes; the old `pulse-glow` is retired (too flashy). Always honor
`prefers-reduced-motion: reduce` by disabling non-essential animation.
