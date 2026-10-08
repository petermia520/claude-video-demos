# Claude Video Demos

Code-generated animation demos.

## Jumbo Joyride — elephant motorcycle animation

Open [jumbo-joyride.html](jumbo-joyride.html) locally in a modern browser. This original Claude-generated demo is a self-contained HTML file with inline SVG, CSS animation, and JavaScript. No build step, package installation, or external assets are required.

The scene includes an elephant riding an orange motorcycle, spinning wheels, a fluttering scarf, and a scrolling landscape. Its animation cycles share a six-second loop.

For frame capture, call `window.renderFrame(t)` in the browser console, where `t` is the time in seconds. Call `window.resumeAnimation()` to resume playback. This demo is an HTML animation, not an encoded video file.

## Spotlight / 《聚光灯》

The existing Spotlight demo remains in the repository:

- [render.py](render.py): code that generates the visuals and soundtrack
- [spotlight.mp4](spotlight.mp4): the rendered 96-second vertical short about the spotlight effect
