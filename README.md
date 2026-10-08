# Claude Video Demos

A collection of code-generated video and animation demos. Each demo lives in its own folder.

## Demos

- [Spotlight / 《聚光灯》](spotlight/): a 96-second vertical short about the spotlight effect, with code-generated visuals and music
- [Jumbo Joyride](jumbo-joyride/): an elephant motorcycle animation generated with Claude

## Jumbo Joyride — elephant motorcycle animation

Open [jumbo-joyride/jumbo-joyride.html](jumbo-joyride/jumbo-joyride.html) locally in a modern browser. This original Claude-generated demo is a self-contained HTML file with inline SVG, CSS animation, and JavaScript. No build step, package installation, or external assets are required.

The scene includes an elephant riding an orange motorcycle, spinning wheels, a fluttering scarf, and a scrolling landscape. Its animation cycles share a six-second loop.

For frame capture, call `window.renderFrame(t)` in the browser console, where `t` is the time in seconds. Call `window.resumeAnimation()` to resume playback. This demo is an HTML animation, not an encoded video file.

## Spotlight / 《聚光灯》

- [spotlight/render.py](spotlight/render.py): code that generates the visuals and soundtrack
- [spotlight/spotlight.mp4](spotlight/spotlight.mp4): the rendered 96-second vertical short (1080 × 1920, 30 fps)

To render the video, run from the demo folder:

```sh
cd spotlight
python3 render.py
```

To preview individual frames, run `python3 render.py --still 25 30.5` from the same folder. Outputs are written to the current working directory.

The renderer requires Python 3, NumPy, Pillow, FFmpeg with libx264 and AAC support, and the Noto CJK fonts at the paths defined by `SERIF` and `SANS` in `render.py`.
