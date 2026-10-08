"""《聚光灯》—— 一个关于"聚光灯效应"的心理学小故事。
竖屏 1080x1920 / 30fps，画面与配乐全部由代码生成。
用法: python3 render.py [输出.mp4]      预览单帧: python3 render.py --still 25 30.5 ...
"""
import math, random, subprocess, sys, wave
from functools import lru_cache
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, DUR = 1080, 1920, 30, 96.0
SERIF = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
SANS = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

INK = (238, 233, 222)
AMBER = (242, 181, 68)
ALARM = (255, 112, 96)
WARM = np.array([1.0, 0.93, 0.78], np.float32)
HAZE = np.array([70, 58, 36], np.float32)


# ---------------------------------------------------------------- 工具函数
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def ease(x):
    x = clamp(x); return x * x * (3 - 2 * x)

def eio(x):
    x = clamp(x); return 0.5 - 0.5 * math.cos(math.pi * x)

def lerp(a, b, x):
    return a + (b - a) * x

def win(t, a, b, fi=0.5, fo=0.5):
    """时间窗 [a,b] 内的淡入淡出透明度。"""
    if t < a or t > b:
        return 0.0
    return min(clamp((t - a) / fi), clamp((b - t) / fo))


@lru_cache(maxsize=None)
def font(serif, size):
    path = SERIF if serif else SANS
    for i in range(12):
        try:
            f = ImageFont.truetype(path, size, index=i)
        except Exception:
            break
        if " SC" in f.getname()[0]:
            return f
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=1024)
def text_img(text, size, color, serif, stroke):
    f = font(serif, size)
    x0, y0, x1, y1 = f.getbbox(text, stroke_width=stroke)
    im = Image.new("RGBA", (x1 - x0 + 24, y1 - y0 + 24), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((12 - x0, 12 - y0), text, font=f, fill=color,
                            stroke_width=stroke, stroke_fill=(8, 8, 12, 210))
    return im


def put_text(cv, text, x, y, size, color=INK, alpha=1.0, serif=False, stroke=0, anchor="c"):
    if alpha <= 0.01:
        return
    im = text_img(text, size, tuple(color), serif, stroke)
    if alpha < 0.999:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    px = x - im.width / 2 if anchor == "c" else x - 12
    py = y - im.height / 2
    cv.alpha_composite(im, (int(max(0, px)), int(max(0, py))))


# ---------------------------------------------------------------- 预计算素材
def _gradient(top, bottom):
    g = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    arr = np.array(top, np.float32) * (1 - g) + np.array(bottom, np.float32) * g
    return np.repeat(arr, W, axis=1)

BG = Image.fromarray(_gradient((52, 60, 84), (86, 90, 108)).astype(np.uint8))

_rng = random.Random(7)
SKYLINE, _x = [], -1600
while _x < 2700:
    w = _rng.randint(120, 260)
    SKYLINE.append((_x, 1080 - _rng.randint(160, 520), _x + w - 8, 1080))
    _x += w


def _make_spot():
    w, h, foot = 800, 1700, 1550
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    cx = w // 2
    d.polygon([(cx - 80, 0), (cx + 80, 0), (cx + 310, foot), (cx - 310, foot)], fill=95)
    d.polygon([(cx - 50, 0), (cx + 50, 0), (cx + 210, foot), (cx - 210, foot)], fill=235)
    d.ellipse([cx - 320, foot - 75, cx + 320, foot + 75], fill=255)
    im = im.filter(ImageFilter.GaussianBlur(28))
    ramp = np.clip(np.linspace(-0.15, 1.6, h, dtype=np.float32), 0, 1)[:, None]
    arr = np.asarray(im, np.float32) / 255 * ramp
    return Image.fromarray((arr * 255).astype(np.uint8)), cx, foot

SPOT_IMG, SPOT_CX, SPOT_FOOT = _make_spot()
_spot_cache = {}

def spot_sprite(z):
    key = round(z, 3)
    if key not in _spot_cache:
        if len(_spot_cache) > 40:
            _spot_cache.clear()
        s = SPOT_IMG.resize((max(1, int(SPOT_IMG.width * z)), max(1, int(SPOT_IMG.height * z))), Image.BILINEAR)
        _spot_cache[key] = np.asarray(s, np.float32) / 255
    return _spot_cache[key]


def _glow(R):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return np.exp(-(((xx - 540) ** 2 + (yy - 880) ** 2) / R ** 2))

GLOW = _glow(520)


# ---------------------------------------------------------------- 角色
def draw_person(d, sx, sy, k, shirt, hair=(42, 34, 32), pants=(42, 46, 60), skin=(226, 192, 162),
                walk=None, stain=0.0, mood=0.0, look=(0, 0), cup=False):
    sw = math.sin(walk) if walk is not None else 0.0
    hip = sy - 150 * k
    for side, ph in ((-1, 1), (1, -1)):
        o = ph * sw * 26 * k
        hx = sx + side * 30 * k
        d.line([(hx, hip), (hx + o, sy - 8 * k)], fill=pants, width=max(2, int(40 * k)))
        d.ellipse([hx + o - 26 * k, sy - 18 * k, hx + o + 26 * k, sy + 6 * k], fill=(28, 28, 34))
    # 手臂
    hands = []
    for side, ph in ((-1, -1), (1, 1)):
        o = ph * sw * 18 * k
        shx, shy = sx + side * 70 * k, sy - 318 * k
        hx, hy = sx + side * 96 * k + o, sy - 182 * k
        if cup and side == 1:
            hx, hy = sx + 104 * k, sy - 214 * k
        d.line([(shx, shy), (hx, hy)], fill=shirt, width=max(2, int(32 * k)))
        d.ellipse([hx - 15 * k, hy - 15 * k, hx + 15 * k, hy + 15 * k], fill=skin)
        hands.append((hx, hy))
    d.rounded_rectangle([sx - 80 * k, sy - 342 * k, sx + 80 * k, sy - 128 * k], radius=42 * k, fill=shirt)
    if stain > 0.2:
        cx, cy, r = sx + 30 * k, sy - 262 * k, stain * k
        brown = (112, 72, 42)
        d.ellipse([cx - r, cy - r * 0.9, cx + r, cy + r * 0.9], fill=brown)
        for i, (ang, rr, dd) in enumerate(((0.3, .35, 1.0), (1.9, .28, 1.05), (3.4, .3, .95), (4.6, .22, 1.1), (5.6, .25, 1.0))):
            px, py = cx + math.cos(ang) * r * dd, cy + math.sin(ang) * r * dd * 0.9
            d.ellipse([px - r * rr, py - r * rr, px + r * rr, py + r * rr], fill=brown)
    if cup:
        hx, hy = hands[1]
        d.rectangle([hx - 17 * k, hy - 52 * k, hx + 17 * k, hy + 4 * k], fill=(198, 158, 112))
        d.rectangle([hx - 20 * k, hy - 60 * k, hx + 20 * k, hy - 50 * k], fill=(244, 242, 236))
    # 头
    d.rectangle([sx - 15 * k, sy - 362 * k, sx + 15 * k, sy - 336 * k], fill=skin)
    r, hy = 58 * k, sy - 410 * k
    d.ellipse([sx - r, hy - r, sx + r, hy + r], fill=skin)
    d.pieslice([sx - r - 4 * k, hy - r - 6 * k, sx + r + 4 * k, hy + r - 4 * k], 180, 360, fill=hair)
    lx, ly = look
    er = max(1.5, 6.5 * k)
    for side in (-1, 1):
        ex, ey = sx + side * 21 * k + lx * k, hy + 10 * k + ly * k
        d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=(30, 26, 28))
    if mood < -0.3:
        for side in (-1, 1):
            d.line([(sx + side * 32 * k, hy - 4 * k), (sx + side * 11 * k, hy - 10 * k)], fill=hair, width=max(1, int(4 * k)))
    my, lw = hy + 34 * k, max(1, int(4.5 * k))
    if mood > 0.15:
        d.arc([sx - 17 * k, my - 16 * k, sx + 17 * k, my + 6 * k], 25, 155, fill=(120, 60, 56), width=lw)
    elif mood < -0.15:
        d.arc([sx - 14 * k, my, sx + 14 * k, my + 16 * k], 205, 335, fill=(120, 60, 56), width=lw)
    else:
        d.line([(sx - 11 * k, my), (sx + 11 * k, my)], fill=(120, 60, 56), width=lw)


CROWD = [  # 世界坐标(脚), 衬衫, 头发, 心里话
    (540, -380, (96, 140, 132), (60, 40, 30), "牙上不会粘着菜叶吧"),
    (-380, 300, (176, 110, 120), (30, 26, 26), "我今天发型好奇怪"),
    (1460, 260, (110, 128, 176), (70, 52, 40), "刚才那句话说错了吗"),
    (-420, 1500, (196, 170, 96), (36, 30, 30), "我是不是又胖了"),
    (1500, 1450, (130, 100, 160), (90, 70, 50), "他们会觉得我很无聊吧"),
    (-150, 2340, (90, 150, 170), (40, 34, 30), "我的声音听起来好怪"),
    (1250, 2380, (170, 120, 90), (28, 24, 24), "鞋子是不是有点脏"),
]

PASSERS = [((180, 190, 205), 0, 130), ((150, 160, 180), 520, -110), ((200, 185, 170), 1000, 95)]

EYES = [(150, 430, 104), (930, 380, 92), (110, 900, 82), (972, 860, 112), (200, 1360, 96),
        (880, 1330, 88), (330, 220, 72), (760, 190, 78), (540, 120, 62), (80, 640, 66),
        (1000, 610, 70), (250, 1570, 72), (830, 1570, 76)]

WORRIES = ["他们一定在笑我", "太丢人了", "怎么偏偏是今天", "所有人都看见了",
           "要不要回家换一件", "完了完了", "开会时大家都会盯着它", "我怎么这么笨"]
_wr = random.Random(3)
WORRY_POS = [(_wr.randint(230, 850), _wr.choice([_wr.randint(250, 560), _wr.randint(1250, 1560)]),
              _wr.randint(54, 84)) for _ in WORRIES]


# ---------------------------------------------------------------- 时间线状态
def camera(t):
    if t < 20 or t >= 80:
        z, cx, cy = 1.0, 540.0, 960.0
    elif t < 32:
        u = eio((t - 20) / 12)
        z, cx, cy = lerp(1.0, 1.25, u), 540.0, lerp(960, 1000, u)
    elif t < 44:
        z, cx, cy = lerp(1.25, 1.4, eio((t - 32) / 10)), 540.0, 1000.0
        a = 9 * ease((t - 32) / 9.5) if t < 41.8 else 0
        cx += math.sin(t * 53) * a / z
        cy += math.cos(t * 47) * a / z
    else:
        z, cx, cy = lerp(1.4, 0.45, eio((t - 44.6) / 9.4)), 540.0, 1000.0
    return z, cx, cy


def ambient(t):
    if t < 20: return 1.0
    if t < 32: return lerp(1.0, 0.1, clamp((t - 20) / 0.12))
    if t < 42: return lerp(0.1, 0.05, (t - 32) / 10)
    if t < 44: return 0.03
    if t < 80: return lerp(0.03, 0.09, clamp((t - 44) / 2))
    return lerp(0.1, 1.0, eio((t - 80.8) / 2.8))


def ayao(t):
    x, walk = 540.0, None
    if t < 15:
        x, walk = lerp(150, 540, eio((t - 11) / 4)), (t * 7.5 if t < 14.8 else None)
    elif t >= 85.8:
        x, walk = lerp(540, 1500, clamp((t - 85.8) / 4.2)), t * 7.5
    stain = 0.0
    if t >= 15.3: stain = 10 * ease((t - 15.3) / 0.25)
    if 32 <= t < 44: stain = lerp(10, 72, ease((t - 32) / 9.5))
    if 44 <= t < 80: stain = lerp(72, 10, eio((t - 45) / 8))
    if t >= 80: stain = 10
    if t < 15.3: mood = 0.4
    elif t < 32: mood = -0.6
    elif t < 50: mood = -1.0
    elif t < 80: mood = lerp(-1.0, 0.0, clamp((t - 52) / 4))
    else: mood = lerp(0.0, 1.0, clamp((t - 82) / 2))
    look = (4, 7) if (15.3 <= t < 54 or 80 <= t < 82) else (0, 0)
    return x, walk, stain, mood, look


def spot_level(t):
    if t < 20: return 0.0
    if t < 20.45:
        return [1, 0.2, 1, 0.5, 1][int((t - 20) / 0.09) % 5]
    return 1.0


# ---------------------------------------------------------------- 场景渲染
def render_world(t):
    z, cx, cy = camera(t)
    amb = ambient(t)
    to_s = lambda wx, wy: (W / 2 + (wx - cx) * z, H / 2 + (wy - cy) * z)
    img = BG.copy()
    d = ImageDraw.Draw(img)
    if t < 20 or t >= 80:
        for x0, y0, x1, y1 in SKYLINE:
            a, b = to_s(x0, y0); c, e = to_s(x1, y1)
            d.rectangle([a, b, c, e], fill=(62, 70, 96))
        a, b = to_s(-3000, 1080)
        d.rectangle([0, b, W, H], fill=(74, 78, 94))
        for shirt, x0, v in PASSERS:
            px = (x0 + v * t) % 1700 - 300
            sx, sy = to_s(px, 1090)
            draw_person(d, sx, sy, 0.6 * z, shirt, walk=t * 6 + x0, mood=0.0)
    crowd_on = 44 <= t < 80
    if crowd_on:
        for wx, wy, shirt, hair, _ in CROWD:
            sx, sy = to_s(wx, wy)
            draw_person(d, sx, sy, z, shirt, hair=hair, mood=-0.5, look=(0, 7))
    x, walk, stain, mood, look = ayao(t)
    sx, sy = to_s(x, 1150)
    draw_person(d, sx, sy, z, (244, 241, 234), walk=walk, stain=stain, mood=mood, look=look, cup=True)
    if 15.0 <= t < 15.3:  # 一滴咖啡
        u = (t - 15.0) / 0.3
        px = lerp(sx + 104 * z, sx + 30 * z, u)
        py = lerp(sy - 270 * z, sy - 262 * z, u) - math.sin(math.pi * u) * 50 * z
        d.ellipse([px - 7 * z, py - 7 * z, px + 7 * z, py + 7 * z], fill=(112, 72, 42))

    arr = np.asarray(img, np.float32)
    if amb < 0.999:
        mask = np.zeros((H, W), np.float32)
        lights = [(x, 1150, spot_level(t))]
        if crowd_on:
            lights += [(wx, wy, clamp((t - (45.6 + i * 0.7)) / 0.12)) for i, (wx, wy, *_r) in enumerate(CROWD)]
        for wx, wy, lv in lights:
            if lv <= 0: continue
            sp = spot_sprite(z)
            lx, ly = to_s(wx, wy)
            ox, oy = int(lx - SPOT_CX * z), int(ly - SPOT_FOOT * z)
            x0, y0 = max(0, ox), max(0, oy)
            x1, y1 = min(W, ox + sp.shape[1]), min(H, oy + sp.shape[0])
            if x1 <= x0 or y1 <= y0: continue
            np.maximum(mask[y0:y1, x0:x1], sp[y0 - oy:y1 - oy, x0 - ox:x1 - ox] * lv, out=mask[y0:y1, x0:x1])
        dk = 1 - amb
        tint = np.array([1 - 0.2 * dk, 1 - 0.08 * dk, 1 + 0.12 * dk], np.float32)
        arr = arr * (amb * tint + (dk * mask)[..., None] * WARM) + (dk * mask * 0.3)[..., None] * HAZE
    cv = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")

    # 黑暗中的眼睛
    if 21 <= t < 47:
        draw_eyes(cv, t, 21, 44.4, 46.0, sx + 30 * z, sy - 262 * z, grow=ease((t - 32) / 9) if t < 44 else 1)

    # 内心独白
    if 32 <= t < 42:
        for i, (w, (px, py, s)) in enumerate(zip(WORRIES, WORRY_POS)):
            t0 = 32.4 + i * 1.12
            a = win(t, t0, t0 + 2.3, 0.15, 0.5)
            j = 4 * math.sin(t * 41 + i)
            put_text(cv, w, px + j, py + j * 0.6, s, ALARM, a, serif=True, stroke=3)

    # 每个人的心里话
    if 50 <= t < 58:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        texts = []
        for i, (wx, wy, _s, _h, msg) in enumerate(CROWD):
            a = win(t, 50.6 + i * 0.55, 57.7, 0.35, 0.4)
            if a <= 0: continue
            hx, hy = to_s(wx, wy - 470)
            ti = text_img(msg, 30, (36, 36, 44), False, 0)
            bw, bh = ti.width + 26, ti.height + 16
            bx = clamp(hx - bw / 2, 18, W - 18 - bw)
            by = hy - bh - 26
            od.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh / 2, fill=(246, 242, 232, int(235 * a)))
            for rr, dy in ((9, 10), (5, 26)):
                od.ellipse([hx - rr, by + bh + dy - rr, hx + rr, by + bh + dy + rr], fill=(246, 242, 232, int(235 * a)))
            texts.append((msg, bx + bw / 2, by + bh / 2, a))
        cv.alpha_composite(ov)
        for msg, x, y, a in texts:
            put_text(cv, msg, x, y, 30, (36, 36, 44), a)

    return cv


def draw_eyes(cv, t, t_in, t_out, t_gone, tx, ty, gap=0.42, grow=0.0):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for i, (ex, ey, s) in enumerate(EYES):
        a = clamp((t - t_in - i * gap) / 0.5) * (1 - clamp((t - t_out) / (t_gone - t_out)))
        if a <= 0: continue
        s *= 1 + 0.12 * grow
        ph = (t * 0.31 + i * 0.37) % 1
        op = 0.08 if ph < 0.035 else 1.0
        h = s * 0.48 * op
        od.ellipse([ex - s / 2, ey - h / 2, ex + s / 2, ey + h / 2], fill=(236, 230, 218, int(235 * a)))
        if op > 0.5:
            dx, dy = tx - ex, ty - ey
            n = math.hypot(dx, dy) or 1
            px, py = ex + dx / n * s * 0.2, ey + dy / n * s * 0.08
            pr = min(s * 0.17, h * 0.45)
            od.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(16, 14, 18, int(255 * a)))
    cv.alpha_composite(ov)


def card_base(glow=0.0, color=AMBER):
    arr = np.empty((H, W, 3), np.float32)
    arr[:] = (13, 14, 19)
    if glow > 0:
        arr += GLOW[..., None] * np.array(color, np.float32) * 0.22 * glow
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def render_intro(t):
    if t < 7:
        cv = card_base()
        draw_eyes(cv, t, 0.5, 6.0, 7.0, 540, 900, gap=0.38)
        return cv
    g = 0 if t < 7.5 else ([1, 0.25, 1, 0.6, 1][int((t - 7.5) / 0.08)] if t < 7.9 else 1)
    cv = card_base(g * 2.2)
    a = win(t, 7.5, 10.8, 0.2, 0.6)
    put_text(cv, "聚光灯", 540, 860, 210, (252, 238, 210), a, True)
    put_text(cv, "一个心理学小故事", 540, 1040, 40, (190, 182, 166), win(t, 8.4, 10.8, 0.6, 0.6))
    return cv


def tshirt(d, cx, cy, a):
    s = 1.0
    pts = [(-70, -110), (-30, -122), (30, -122), (70, -110), (150, -60), (118, 0), (80, -24),
           (80, 120), (-80, 120), (-80, -24), (-118, 0), (-150, -60)]
    d.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=(238, 232, 220, int(255 * a)))
    d.arc([cx - 30, cy - 132, cx + 30, cy - 100], 0, 180, fill=(13, 14, 19, int(255 * a)), width=6)
    d.ellipse([cx - 42, cy - 40, cx + 42, cy + 44], fill=(240, 170, 90, int(255 * a)))
    d.pieslice([cx - 48, cy - 52, cx + 48, cy + 36], 180, 360, fill=(120, 80, 50, int(255 * a)))
    for ex in (-15, 15):
        d.ellipse([cx + ex - 5, cy - 2, cx + ex + 5, cy + 8], fill=(30, 26, 28, int(255 * a)))
    d.arc([cx - 18, cy + 6, cx + 18, cy + 30], 20, 160, fill=(130, 50, 50, int(255 * a)), width=4)


def render_science(t):
    cv = card_base(0.6, (120, 140, 200))
    out = 1 - clamp((t - 71.5) / 0.5)
    a = clamp((t - 58.6) / 0.6) * out
    if a > 0:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tshirt(ImageDraw.Draw(ov), 540, 700 + 6 * math.sin(t * 2), a)
        cv.alpha_composite(ov)

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    bars = [(62.0, "穿的人以为被注意", 0.50, ALARM, 1200), (65.0, "实际注意到的人", 0.25, AMBER, 1400)]
    texts = []
    for t0, label, v, col, y in bars:
        a = clamp((t - t0) / 0.4) * out
        if a <= 0: continue
        gw = 800 * v * eio((t - t0 - 0.2) / 1.2)
        od.rounded_rectangle([140, y, 940, y + 64], radius=10, fill=(38, 40, 52, int(255 * a)))
        if gw > 4:
            od.rounded_rectangle([140, y, 140 + gw, y + 64], radius=10, fill=col + (int(255 * a),))
        texts.append((label, y, a, col, f"约 {round(100 * v * eio((t - t0 - 0.2) / 1.2))}%"))
    cv.alpha_composite(ov)
    for label, y, a, col, val in texts:
        put_text(cv, label, 140, y - 46, 38, INK, a, anchor="l")
        put_text(cv, val, 940 - 150, y - 46, 38, col, a, anchor="l")
    put_text(cv, "Gilovich, Medvec & Savitsky (2000), Journal of Personality and Social Psychology",
             540, 1820, 22, (120, 118, 112), clamp((t - 64.2) / 0.6) * out)
    return cv


def render_name(t):
    g = eio((t - 72.3) / 2.2)
    cv = card_base(g * 2.0)
    out = 1 - clamp((t - 79.4) / 0.6)
    put_text(cv, "聚光灯效应", 540, 880, 150, (252, 236, 200), clamp((t - 73.8) / 0.4) * out, True)
    put_text(cv, "THE  SPOTLIGHT  EFFECT", 540, 1020, 34, AMBER, clamp((t - 74.6) / 0.6) * out)
    return cv


def render_end(t):
    cv = card_base(eio((t - 89.5) / 2) * 1.6)
    put_text(cv, "聚光灯效应", 540, 880, 120, (252, 236, 200), clamp((t - 90.2) / 0.8), True)
    put_text(cv, "THE  SPOTLIGHT  EFFECT", 540, 1000, 32, AMBER, clamp((t - 91.0) / 0.8))
    return cv


def render(t):
    if t < 11: cv = render_intro(t)
    elif t < 58: cv = render_world(t)
    elif t < 72: cv = render_science(t)
    elif t < 80: cv = render_name(t)
    elif t < 89.5: cv = render_world(t)
    else: cv = render_end(t)
    g = 1.0
    for a, b in ((10.7, 11.5), (57.5, 58.3), (79.6, 80.4), (89.0, 89.8)):
        m = (a + b) / 2
        if a <= t < b:
            g = clamp(abs(t - m) / ((b - a) / 2))
    g *= 1 - clamp((t - 95.0) / 1.0)
    arr = np.asarray(cv.convert("RGB"))
    if g < 0.999:
        arr = (arr.astype(np.float32) * g).astype(np.uint8)
    return arr


def frame_bytes(i):
    return render(i / FPS).tobytes()


# ---------------------------------------------------------------- 配乐
def make_audio(path):
    sr = 44100
    n = int(DUR * sr)
    tt = np.arange(n) / sr
    out = np.zeros(n)

    def env(t0, t1, fi, fo):
        e = np.clip((tt - t0) / fi, 0, 1) * np.clip((t1 - tt) / fo, 0, 1)
        return e

    def pad(freqs, t0, t1, vol, fi=2.0, fo=2.0):
        e = env(t0, t1, fi, fo)
        s = sum(np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * f * 1.004 * tt) + 0.2 * np.sin(4 * np.pi * f * tt) for f in freqs)
        lfo = 0.8 + 0.2 * np.sin(2 * np.pi * 0.13 * tt)
        return s * e * lfo * vol / len(freqs)

    def hit(t0, dur, f, vol, decay, harm=0.3):
        i0, i1 = int(t0 * sr), min(n, int((t0 + dur) * sr))
        u = np.arange(i1 - i0) / sr
        out[i0:i1] += vol * np.exp(-u / decay) * (np.sin(2 * np.pi * f * u) + harm * np.sin(4 * np.pi * f * u))

    rng = np.random.default_rng(1)

    def clunk(t0, vol):
        i0 = int(t0 * sr); m = int(0.35 * sr)
        nz = rng.standard_normal(m)
        nz = np.convolve(nz, np.ones(30) / 30, "same")
        u = np.arange(m) / sr
        out[i0:i0 + m] += vol * (nz * 3 * np.exp(-u / 0.04) + np.sin(2 * np.pi * 70 * u) * np.exp(-u / 0.12))

    out += pad([110, 164.81, 261.63], 0, 20.2, 0.16, 3, 0.3)
    out += pad([130.81, 196, 329.63], 7.5, 11.2, 0.08, 0.5, 0.6)
    # 黑暗与紧张
    out += pad([55, 82.41, 116.54], 20, 42, 0.2, 0.2, 0.05)
    sweep = env(32, 42, 4, 0.05) * np.sin(2 * np.pi * (380 * (tt - 32) + 22 * (tt - 32) ** 2)) * 0.035
    out += sweep
    clunk(7.5, 0.5)
    clunk(20.0, 0.8)
    for i in range(len(CROWD)):
        clunk(45.6 + i * 0.7, 0.35)
    tb = 20.6
    while tb < 41.8:
        p = clamp((tb - 20.6) / 21)
        hit(tb, 0.3, 52, 0.55 + 0.2 * p, 0.07, 0.1)
        hit(tb + 0.17, 0.3, 48, 0.4 + 0.2 * p, 0.07, 0.1)
        tb += lerp(0.9, 0.42, p)
    # 揭示与释然
    out += pad([87.31, 220, 261.63], 44.5, 58, 0.15, 3, 0.6)
    out += pad([130.81, 196, 329.63], 58, 80, 0.12, 0.8, 0.6)
    out += pad([130.81, 164.81, 196, 392], 80.2, DUR, 0.14, 2.5, 3)
    scale = [523.25, 587.33, 659.25, 783.99, 880.0, 1046.5]
    mr = random.Random(5)
    for start, end, step in ((58.4, 71.5, 0.5), (80.8, 94.5, 0.6), (45.5, 57, 1.0)):
        x = start
        while x < end:
            if mr.random() < 0.75:
                hit(x, 1.2, mr.choice(scale), 0.06, 0.35)
            x += step
    hit(73.8, 3, 880, 0.18, 1.0, 0.5); hit(73.8, 3, 1318.5, 0.1, 0.8)
    hit(91.3, 3, 659.25, 0.12, 1.0, 0.5); hit(91.3, 3, 987.77, 0.08, 0.9)
    out *= np.clip((DUR - tt) / 1.5, 0, 1)
    out = np.tanh(out * 1.2)
    out = out / np.max(np.abs(out)) * 0.85
    pcm = (out * 32767).astype(np.int16)
    st = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(st.tobytes())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--still":
        for s in sys.argv[2:]:
            Image.fromarray(render(float(s))).save(f"still_{s}.png")
        sys.exit()
    out = sys.argv[1] if len(sys.argv) > 1 else "spotlight.mp4"
    make_audio("audio.wav")
    N = int(DUR * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", "audio.wav",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out],
                          stdin=subprocess.PIPE)
    with Pool() as pool:
        for i, b in enumerate(pool.imap(frame_bytes, range(N), chunksize=6)):
            ff.stdin.write(b)
            if i % 300 == 0:
                print(f"{i}/{N}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done", out)
