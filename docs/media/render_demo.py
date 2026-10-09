#!/usr/bin/env python3
"""The django-admin-mcp demo film, rendered deterministically with Pillow.

No Django project, browser or network access is needed. Requires Pillow, NumPy
and FFmpeg. Every frame is a pure function of time, so the film is reproducible.

    uv run --with pillow --with numpy python docs/media/render_demo.py --output docs/media/demo.mp4
    uv run --with pillow --with numpy python docs/media/render_demo.py --storyboard storyboard.jpg
    uv run --with pillow --with numpy python docs/media/render_demo.py --frame 30.5 --output frame.png

``--output demo.mp4`` also writes ``demo.gif``, the README preview, beside it.
The soundtrack comes from ``demo_audio.py`` in this directory.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from functools import cache, lru_cache
from multiprocessing import Pool
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

W, H, FPS, DURATION = 1920, 1080, 60, 50
BG = (8, 13, 12)
INK = (240, 244, 241)
GREEN = (68, 183, 139)  # Django's brand green
MINT = (150, 232, 196)
VIOLET = (150, 134, 240)  # the agent side
AMBER = (255, 196, 84)
CORAL = (255, 112, 92)
MUTED = (148, 160, 154)
DIM = (66, 78, 72)
RULE = (32, 44, 39)
CARD = (16, 24, 21)
STARTS = (0, 6, 14, 22, 28, 40, 46)
ENDS = STARTS[1:] + (DURATION,)
CHAPTERS = (
    "YOUR ADMIN, AS TOOLS",
    "ONE MIXIN",
    "THROUGH THE ADMIN",
    "ONE TOKEN",
    "ASK THE AGENT",
    "GET STARTED",
    "DJANGO-ADMIN-MCP",
)
WIPE = 0.7
TOOLS = (
    "list_article",
    "get_article",
    "create_article",
    "update_article",
    "delete_article",
    "bulk_article",
    "actions_article",
    "action_article",
    "describe_article",
    "related_article",
    "history_article",
    "autocomplete_article",
)


# Maths -----------------------------------------------------------------------


def clamp(x):
    return min(1.0, max(0.0, x))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def mix(a, b, p):
    p = clamp(p)
    return tuple(round(x + (y - x) * p) for x, y in zip(a, b, strict=True))


# Type ------------------------------------------------------------------------

FONT_DIRS = (
    Path("/usr/share/fonts/TTF"),
    Path("/usr/share/fonts/truetype/fira"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/dejavu"),
    Path.home() / ".local/share/fonts",
    Path.home() / ".fonts",
)
FACES = {
    "light": ("FiraSans-Light.ttf", "DejaVuSans-ExtraLight.ttf", "DejaVuSans.ttf"),
    "regular": ("FiraSans-Regular.ttf", "DejaVuSans.ttf"),
    "medium": ("FiraSans-Medium.ttf", "DejaVuSans.ttf"),
    "semibold": ("FiraSans-SemiBold.ttf", "DejaVuSans-Bold.ttf"),
    "bold": ("FiraSans-Bold.ttf", "DejaVuSans-Bold.ttf"),
    "mono": ("DejaVuSansMono.ttf",),
    "monobold": ("DejaVuSansMono-Bold.ttf", "DejaVuSansMono.ttf"),
}


@cache
def font(size, weight="regular"):
    for name in FACES[weight]:
        for root in FONT_DIRS:
            if (root / name).exists():
                return ImageFont.truetype(str(root / name), size)
    raise RuntimeError(f"No font found for {weight!r}; install Fira Sans or DejaVu")


@lru_cache(maxsize=4000)
def lettering(value, size, color, weight):
    """Text on a transparent stamp whose top is the font's ascender, so segments line up."""
    f = font(size, weight)
    box = f.getbbox(value)
    ascent, descent = f.getmetrics()
    im = Image.new("RGBA", (max(1, box[2] - box[0] + 4), ascent + descent + 4))
    ImageDraw.Draw(im).text((2 - box[0], 2), value, font=f, fill=color)
    return im


def width_of(value, size, weight="regular"):
    return font(size, weight).getlength(value)


def txt(im, x, y, value, size=32, color=INK, weight="regular", align="left", opacity=1.0):
    if opacity <= 0 or not value:
        return
    stamp = lettering(value, size, color, weight)
    if align == "center":
        x -= stamp.width / 2
    elif align == "right":
        x -= stamp.width
    if opacity < 1:
        stamp = stamp.copy()
        stamp.putalpha(stamp.getchannel("A").point(lambda v: round(v * opacity)))
    im.paste(stamp, (round(x), round(y)), stamp)


def reveal(im, x, y, value, size, local, at=0.0, color=INK, weight="bold", align="left", rise=28):
    p = ease((local - at) / 0.6)
    txt(im, x, y + rise * (1 - p), value, size, color, weight, align, p)


def typed(im, x, y, value, size, local, at=0.0, color=INK, weight="regular", speed=28.0):
    """Text that appears character by character, with a cursor while it types."""
    if local < at:
        return 0
    shown = min(len(value), int((local - at) * speed))
    txt(im, x, y, value[:shown], size, color, weight)
    if shown < len(value) and int(local * 3) % 2 == 0:
        cx = x + width_of(value[:shown], size, weight) + 2
        ImageDraw.Draw(im).rectangle((cx, y + 2, cx + 3, y + size), fill=color)
    return shown


# Shapes ----------------------------------------------------------------------


def draw(im):
    return ImageDraw.Draw(im)


def rect(im, box, fill=CARD, outline=None, width=1, radius=14):
    draw(im).rounded_rectangle(tuple(round(v) for v in box), radius=radius, fill=fill, outline=outline, width=width)


def line(im, xy, fill=RULE, width=2):
    draw(im).line(tuple(round(v) for v in xy), fill=fill, width=width)


def arrow(im, x0, y0, x1, y1, color=GREEN, width=4):
    line(im, (x0, y0, x1, y1), color, width)
    angle = math.atan2(y1 - y0, x1 - x0)
    head = [(x1 + 4 * math.cos(angle), y1 + 4 * math.sin(angle))]
    head += [(x1 - 16 * math.cos(angle + a), y1 - 16 * math.sin(angle + a)) for a in (-0.5, 0.5)]
    draw(im).polygon(head, fill=color)


def check(im, cx, cy, color=GREEN, size=12, width=4):
    draw(im).line(
        [(cx - size, cy), (cx - size * 0.3, cy + size * 0.7), (cx + size, cy - size * 0.8)],
        fill=color,
        width=width,
        joint="curve",
    )


def cross(im, cx, cy, color=CORAL, size=10, width=4):
    line(im, (cx - size, cy - size, cx + size, cy + size), color, width)
    line(im, (cx - size, cy + size, cx + size, cy - size), color, width)


def chip(im, x, y, value, size=24, color=GREEN, weight="mono", opacity=1.0, pad=16):
    """A rounded label. Returns its width so callers can flow chips."""
    w = width_of(value, size, weight) + pad * 2
    if opacity > 0:
        rect(im, (x, y, x + w, y + size + 18), mix(BG, CARD, opacity), mix(BG, mix(DIM, color, 0.5), opacity), 2, 10)
        txt(im, x + pad, y + 8, value, size, color, weight, opacity=opacity)
    return w


@lru_cache(maxsize=1)
def backdrop():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for y in range(H):
        d.line((0, y, W, y), fill=mix(BG, (12, 20, 18), y / H))
    for y in range(36, H, 48):
        for x in range(36, W, 48):
            d.point((x, y), fill=(22, 32, 28))
    return im


@lru_cache(maxsize=1)
def glow_sprite():
    size = 120
    im = Image.new("RGB", (size, size))
    px = im.load()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - size / 2 + 0.5, y - size / 2 + 0.5) / (size / 2)
            a = clamp(1 - d) ** 2.4 * 0.26
            c = mix(VIOLET, GREEN, clamp(1.1 - d))
            px[x, y] = tuple(round(v * a) for v in c)
    return im.resize((1500, 1500), Image.Resampling.BICUBIC)


# Where the light sits in each chapter; it drifts between them.
GLOW = ((1500, 320), (1560, 880), (960, 980), (400, 900), (1560, 700), (300, 260), (960, 560))


def glow_at(t):
    index = next((i for i, end in enumerate(ENDS) if t < end), len(ENDS) - 1)
    local = t - STARTS[index]
    a = GLOW[max(0, index - 1)] if local < 1.6 and index else GLOW[index]
    b = GLOW[index]
    p = smooth(local / 1.6) if index else 1
    return a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p


def base(t):
    layer = Image.new("RGB", (W, H))
    x, y = glow_at(t)
    layer.paste(glow_sprite(), (round(x - 750), round(y - 750)))
    return ImageChops.add(backdrop(), layer)


def title(im, value, local, subtitle=None):
    reveal(im, 100, 150, value, 84, local, at=0.1)
    if subtitle:
        reveal(im, 104, 262, subtitle, 32, local, at=0.3, color=MUTED, weight="regular")


def foot(im, *lines):
    for i, value in enumerate(lines):
        txt(im, 104, 948 + i * 34, value, 24, MUTED, "regular")


def mark(im, x, y, size, opacity=1.0):
    """The badge: a green tile with the curly braces of a tool call."""
    if opacity <= 0:
        return
    rect(im, (x, y, x + size, y + size), mix(BG, GREEN, opacity), radius=round(size * 0.26))
    glyph = lettering("{}", round(size * 0.62), BG, "monobold")
    txt(im, x + size / 2, y + (size - glyph.height) / 2, "{}", round(size * 0.62), BG, "monobold", "center", opacity)


def chrome(im, index, t):
    alpha = 1 - smooth((t - STARTS[-1] - 0.2) / 0.5)
    if alpha > 0:
        mark(im, 104, 58, 42, alpha)
        txt(im, 160, 62, "django-admin-mcp", 30, INK, "bold", opacity=alpha)
        txt(im, 1816, 70, f"{index + 1:02d} / {CHAPTERS[index]}", 22, MUTED, "mono", "right", alpha)
    line(im, (0, 1, W * t / DURATION, 1), GREEN, 3)


def code_card(im, box, lines, local, at=0.0, size=27, stagger=0.12, highlight=()):
    """A code listing whose lines arrive one by one. ``lines`` are segment lists."""
    x0, y0, x1, y1 = box
    p = ease((local - at) / 0.5)
    if p <= 0:
        return
    rect(im, (x0, y0 + 20 * (1 - p), x1, y1 + 20 * (1 - p)), mix(BG, CARD, p), mix(BG, RULE, p), 2, 18)
    for i, c in enumerate((CORAL, AMBER, GREEN)):
        draw(im).ellipse((x0 + 24 + i * 24, y0 + 22, x0 + 36 + i * 24, y0 + 34), fill=mix(BG, c, p * 0.8))
    step = size * 1.55
    for n, segments in enumerate(lines):
        q = ease((local - at - 0.3 - n * stagger) / 0.4)
        if q <= 0:
            continue
        y = y0 + 64 + n * step
        if n in highlight:
            h = ease((local - at - 1.6) / 0.5)
            rect(im, (x0 + 14, y - 6, x1 - 14, y + size + 8), mix(CARD, (24, 48, 38), h * q), radius=8)
            line(im, (x0 + 14, y - 6, x0 + 14, y + size + 8), mix(CARD, GREEN, h * q), 4)
        x = x0 + 34
        for value, color in segments:
            txt(im, x, y, value, size, color, "mono", opacity=q)
            x += width_of(value, size, "mono")


def mono(value, color=INK):
    return (value, color)


KW, STR, NAME, PUNC = VIOLET, AMBER, MINT, MUTED


# 1 · Hook --------------------------------------------------------------------


def hook(t):
    t += 0.9  # The first frame already carries the message.
    im = base(t - 0.9)
    reveal(im, 100, 186, "Your Django admin,", 120, t, at=0)
    reveal(im, 100, 322, "as MCP tools.", 120, t, at=0.2, color=GREEN)
    reveal(im, 106, 498, "Add a mixin to your ModelAdmin. MCP clients get CRUD, actions and history,", 36, t, at=0.55)
    reveal(
        im,
        106,
        552,
        "inside Django's existing permissions. Only Django and Pydantic as dependencies.",
        30,
        t,
        at=0.7,
        color=MUTED,
        weight="regular",
    )
    p = ease((t - 1.3) / 0.6)
    if p:
        y = 660 + 30 * (1 - p)
        rect(im, (104, y, 1110, y + 230), mix(BG, CARD, p), mix(BG, RULE, p), 2, radius=22)
        txt(im, 144, y + 30, "TOOLS PER EXPOSED MODEL", 22, MUTED, "mono", opacity=p)
        txt(im, 140, y + 62, "12", 120, GREEN, "bold", opacity=p)
        txt(im, 360, y + 88, "generated from the ModelAdmin", 32, INK, "semibold", opacity=p)
        txt(im, 360, y + 140, "you already maintain", 28, MUTED, opacity=p)
    for i, name in enumerate(("list_article", "action_article", "history_article", "describe_article")):
        q = ease((t - 1.7 - i * 0.18) / 0.5)
        if q:
            chip(im, 1400, 500 + i * 86 + 24 * (1 - q), name, 30, GREEN if i % 2 == 0 else VIOLET, opacity=q)
    txt(im, 1400, 850, "+ bulk, related, autocomplete and more", 24, MUTED, "regular", opacity=ease((t - 2.6) / 0.5))
    foot(
        im,
        "Django 3.2 to 5.x · Python 3.10+ · MIT",
        "pip install django-admin-mcp",
    )
    return im


# 2 · One mixin ---------------------------------------------------------------

ADMIN_PY = (
    [mono("from ", KW), mono("django.contrib "), mono("import ", KW), mono("admin")],
    [mono("from ", KW), mono("django_admin_mcp "), mono("import ", KW), mono("MCPAdminMixin", NAME)],
    [mono("from ", KW), mono(".models "), mono("import ", KW), mono("Article")],
    [],
    [mono("@admin.register(Article)", MUTED)],
    [
        mono("class ", KW),
        mono("ArticleAdmin", NAME),
        mono("(", PUNC),
        mono("MCPAdminMixin", NAME),
        mono(", admin.ModelAdmin):", PUNC),
    ],
    [mono("    mcp_expose = "), mono("True", GREEN)],
    [mono("    mcp_exclude_fields = ["), mono('"internal_notes"', STR), mono("]")],
    [
        mono("    list_display = ["),
        mono('"title"', STR),
        mono(", "),
        mono('"author"', STR),
        mono(", "),
        mono('"published"', STR),
        mono("]"),
    ],
)


def mixin(t):
    im = base(t + STARTS[1])
    title(
        im,
        "One mixin.",
        t,
        "Set mcp_expose = True and the tools are generated from the ModelAdmin you already maintain.",
    )
    code_card(im, (104, 350, 980, 790), ADMIN_PY, t, at=0.4, highlight=(5, 6), size=25)
    txt(im, 950, 372, "admin.py", 22, MUTED, "mono", "right", ease((t - 0.6) / 0.5))
    # Tools fan out on the right, three columns.
    p = ease((t - 2.2) / 0.5)
    if p:
        arrow(im, 996, 570, 1056 - 20 * (1 - p), 570, mix(BG, GREEN, p), 4)
    for i, name in enumerate(TOOLS):
        q = ease((t - 2.4 - i * 0.22) / 0.45)
        if q <= 0:
            continue
        col, row = i % 2, i // 2
        x = 1084 + col * 372
        y = 364 + row * 76 + 18 * (1 - q)
        color = (
            GREEN if name.split("_")[0] in ("list", "get", "describe", "related", "history", "autocomplete") else VIOLET
        )
        chip(im, x, y, name, 22, color, opacity=q, pad=14)
    q = ease((t - 5.2) / 0.5)
    txt(im, 1084, 836, "Green reads need view. Violet writes need add, change or delete.", 22, MUTED, opacity=q)
    txt(im, 1084, 870, "Plus find_models, MCP prompts, and models:// and data:// resources.", 22, MUTED, opacity=q)
    foot(
        im,
        "Field choices, querysets, validation, actions and permissions stay in the admin.",
        "The agent inherits every change you make there.",
    )
    return im


# 3 · Through the admin -------------------------------------------------------

GATES = (
    ("Permissions", "has_change_permission()", "held by the token's user"),
    ("Validation", "full_clean()", "the admin form's rules"),
    ("Your hooks", "save_model()", "and save_related() too"),
    ("Audit", "LogEntry", "under the token's user"),
)
GATE_W, GATE_GAP, GATE_Y = 300, 20, 470


def gate_x(i):
    return 380 + i * (GATE_W + GATE_GAP)


def gate_time(i):
    return 1.6 + i * 1.05


def through(t):
    im = base(t + STARTS[2])
    title(
        im,
        "Through the admin, not around it.",
        t,
        "A database connection hands the agent raw tables. The admin already encodes who may touch what.",
    )
    rail_y = 436
    first, last = 170, 1750
    line(im, (first, rail_y, last, rail_y), RULE, 4)
    # Endpoints: the agent and the database.
    for x, label, sub, color in ((first, "Agent", "any MCP client", VIOLET), (last, "Database", "your models", GREEN)):
        p = ease(t / 0.5)
        draw(im).ellipse(
            (x - 44, rail_y - 44, x + 44, rail_y + 44), fill=mix(BG, CARD, p), outline=mix(BG, color, p), width=4
        )
        txt(im, x, rail_y + 60, label, 30, INK, "semibold", "center", p)
        txt(im, x, rail_y + 100, sub, 22, MUTED, "regular", "center", p)
    # The request travels the rail, and each gate lights as it passes.
    start, end = gate_time(0) - 0.9, gate_time(3) + 0.9
    travel = smooth((t - start) / (end - start))
    tx = first + (last - first) * travel
    if t >= start:
        line(im, (first, rail_y, tx, rail_y), GREEN, 4)
    for i, (name, call, detail) in enumerate(GATES):
        x = gate_x(i)
        shown = ease((t - 0.3 - i * 0.12) / 0.5)
        if shown <= 0:
            continue
        lit = ease((t - gate_time(i)) / 0.4)
        y = GATE_Y + 20 * (1 - shown)
        rect(im, (x, y, x + GATE_W, y + 250), mix(BG, CARD, shown), mix(BG, mix(RULE, GREEN, lit), shown), 2, 18)
        rect(
            im, (x + GATE_W / 2 - 3, rail_y - 2, x + GATE_W / 2 + 3, y), mix(BG, mix(RULE, GREEN, lit), shown), radius=2
        )
        txt(im, x + 28, y + 26, name, 34, INK, "semibold", opacity=shown)
        txt(im, x + 28, y + 82, call, 19, mix(MUTED, MINT, lit), "mono", opacity=shown)
        txt(im, x + 28, y + 124, detail, 22, MUTED, "regular", opacity=shown)
        if lit:
            draw(im).ellipse((x + GATE_W - 70, y + 192, x + GATE_W - 30, y + 232), fill=mix(CARD, GREEN, lit))
            check(im, x + GATE_W - 50, y + 212, BG, 9, 4)
    if t >= start:
        chip(im, tx - 110, rail_y - 62, "update_article  id=42", 22, VIOLET)
    foot(
        im,
        "Raw database access skips all of these. The agent uses the operations you designed, not SQL it invented.",
        "Admin actions become tools too, including two-step confirmation flows.",
    )
    return im


# 4 · One token ---------------------------------------------------------------

PERMS = (
    ("blog · article", "Can view", True),
    ("blog · article", "Can change", True),
    ("blog · article", "Can add", True),
    ("blog · article", "Can delete", False),
    ("auth · user", "Can view", False),
)


def token(t):
    im = base(t + STARTS[3])
    title(
        im,
        "One token, one user.",
        t,
        "A token can only do what its linked user can do, and starts with no access until you grant it.",
    )
    p = ease((t - 0.4) / 0.6)
    if p:
        y = 360 + 24 * (1 - p)
        rect(im, (104, y, 900, y + 470), mix(BG, CARD, p), mix(BG, RULE, p), 2, 22)
        txt(im, 140, y + 30, "MCP TOKEN", 22, MUTED, "mono", opacity=p)
        txt(im, 140, y + 68, "mcp_7Qf3kA2b", 40, GREEN, "monobold", opacity=p)
        txt(
            im,
            140 + width_of("mcp_7Qf3kA2b", 40, "monobold"),
            y + 68,
            ".••••••••••••••••••••",
            40,
            DIM,
            "monobold",
            opacity=p,
        )
        txt(im, 140, y + 128, "only a salted hash of the secret is stored", 22, MUTED, opacity=p)
        rows = (("User", "ops-agent"), ("Groups", "Editors"), ("Expires", "2026-12-31"), ("Status", "active"))
        for i, (k, v) in enumerate(rows):
            q = ease((t - 0.9 - i * 0.15) / 0.4)
            yy = y + 190 + i * 62
            line(im, (140, yy - 12, 864, yy - 12), mix(BG, RULE, q), 2)
            txt(im, 140, yy, k, 26, MUTED, opacity=q)
            txt(im, 360, yy, v, 28, INK if k != "Status" else GREEN, "semibold", opacity=q)
    q = ease((t - 1.2) / 0.6)
    if q:
        y = 360 + 24 * (1 - q)
        rect(im, (960, y, 1816, y + 470), mix(BG, CARD, q), mix(BG, RULE, q), 2, 22)
        txt(im, 996, y + 30, "TOKEN PERMISSIONS", 22, MUTED, "mono", opacity=q)
        for i, (scope, perm, granted) in enumerate(PERMS):
            r = ease((t - 1.8 - i * 0.3) / 0.4)
            if r <= 0:
                continue
            yy = y + 84 + i * 72
            box = (996, yy, 1036, yy + 40)
            if granted:
                rect(im, box, mix(CARD, GREEN, r), radius=10)
                check(im, 1016, yy + 20, BG, 9, 4)
            else:
                rect(im, box, mix(CARD, CARD, 1), mix(CARD, DIM, r), 2, 10)
                cross(im, 1016, yy + 20, mix(CARD, DIM, r), 7, 3)
            txt(im, 1060, yy + 2, perm, 30, INK if granted else DIM, "semibold", opacity=r)
            txt(im, 1060 + width_of(perm, 30, "semibold") + 20, yy + 8, scope, 22, MUTED, "mono", opacity=r)
    s = ease((t - 3.6) / 0.6)
    pieces = (
        ("effective permissions  =  token permissions  ", "semibold"),
        ("∩", "monobold"),
        ("  user permissions", "semibold"),
    )
    x = 960 - sum(width_of(v, 30, w) for v, w in pieces) / 2
    for value, weight in pieces:
        txt(im, x, 866, value, 30, MINT, weight, opacity=s)
        x += width_of(value, 30, weight)
    foot(
        im,
        "Deactivate the user and its tokens stop. Revoke a token in the admin. Expiry is configurable.",
        "Sensitive fields stay hidden with mcp_fields and mcp_exclude_fields; get_queryset() still limits the rows.",
    )
    return im


# 5 · Ask the agent -----------------------------------------------------------

CHAT_X, CHAT_W, LOG_X = 104, 1040, 1200

TABLE = (
    ("42", "Getting Started with Django", "Jane Doe", "published"),
    ("41", "Python Best Practices", "John Smith", "published"),
    ("40", "REST API Design", "Jane Doe", "draft"),
)

# (time, kind, text) for the server-side log pane.
LOG = (
    (1.4, "call", "tools/call  list_article  {limit: 10}"),
    (1.7, "ok", "has_view_permission(request)  →  True"),
    (1.9, "ok", "ArticleAdmin.get_queryset()  →  42 rows"),
    (5.4, "call", "tools/call  action_article  {ids: [40]}"),
    (5.7, "ok", "has_change_permission(request)  →  True"),
    (5.9, "ok", "mark_as_published(modeladmin, request, qs)"),
    (6.2, "log", "LogEntry  CHANGE  article 40  user=ops-agent"),
    (9.2, "call", "tools/call  history_article  {id: 40}"),
    (9.5, "ok", "has_view_permission(request)  →  True"),
    (9.7, "ok", "LogEntry.filter(object_id=40)  →  2 entries"),
)


def bubble(im, y, value, local, at, width=None):
    """The user's line, typed into a violet bubble on the right of the column."""
    if local < at:
        return
    p = ease((local - at) / 0.3)
    w = width or width_of(value, 28, "medium") + 56
    x = CHAT_X + CHAT_W - w
    rect(im, (x, y + 10 * (1 - p), x + w, y + 56 + 10 * (1 - p)), mix(BG, mix(CARD, VIOLET, 0.22), p), None, 0, 18)
    typed(im, x + 28, y + 12, value, 28, local, at + 0.1, INK, "medium", speed=30)


def tool_call(im, y, value, local, at):
    p = ease((local - at) / 0.35)
    if p <= 0:
        return
    draw(im).ellipse((CHAT_X + 6, y + 14, CHAT_X + 22, y + 30), fill=mix(BG, GREEN, p))
    chip(im, CHAT_X + 40, y - 2 + 8 * (1 - p), value, 22, GREEN, opacity=p, pad=14)


def reply(im, y, lines, local, at):
    p = ease((local - at) / 0.4)
    for i, (value, color, weight) in enumerate(lines):
        q = ease((local - at - i * 0.12) / 0.4)
        txt(im, CHAT_X + 40, y + i * 38 + 8 * (1 - q), value, 26, color, weight, opacity=q)
    return p


def table(im, y, local, at):
    cols = (CHAT_X + 40, CHAT_X + 110, CHAT_X + 520, CHAT_X + 760)
    p = ease((local - at) / 0.4)
    if p <= 0:
        return
    for x, head in zip(cols, ("ID", "Title", "Author", "Status"), strict=True):
        txt(im, x, y, head, 20, MUTED, "mono", opacity=p)
    line(im, (CHAT_X + 40, y + 34, CHAT_X + CHAT_W - 80, y + 34), mix(BG, RULE, p), 2)
    for i, row in enumerate(TABLE):
        q = ease((local - at - 0.15 - i * 0.12) / 0.35)
        yy = y + 48 + i * 40
        for x, value in zip(cols, row, strict=True):
            color = GREEN if value == "published" else (AMBER if value == "draft" else INK)
            txt(im, x, yy, value, 24, color, "mono" if x == cols[0] else "regular", opacity=q)
    q = ease((local - at - 0.6) / 0.4)
    txt(im, CHAT_X + 40, y + 48 + len(TABLE) * 40 + 6, "… showing 10 of 42 articles", 22, MUTED, opacity=q)


def ask(t):
    im = base(t + STARTS[4])
    title(
        im,
        "Ask the agent.",
        t,
        "Any MCP client that speaks HTTP. The agent calls the tools; the admin decides what happens.",
    )
    # Exchange 1: list.
    bubble(im, 330, "Show me the latest articles", t, 0.4)
    tool_call(im, 402, "list_article  limit=10", t, 1.4)
    table(im, 458, t, 2.0)
    # Exchange 2: an admin action.
    bubble(im, 650, "Publish article 40", t, 4.4)
    tool_call(im, 722, "action_article  action=mark_as_published  ids=[40]", t, 5.4)
    reply(im, 776, (("1 article marked as published.", INK, "regular"),), t, 6.2)
    # Exchange 3: history.
    bubble(im, 836, "What changed on article 40?", t, 8.2)
    tool_call(im, 908, "history_article  id=40", t, 9.2)
    reply(
        im,
        962,
        (
            ("just now · ops-agent · changed is_published, published_date", INK, "regular"),
            ("Jan 13 · jane · created", MUTED, "regular"),
        ),
        t,
        9.9,
    )
    # The server's side of the story.
    p = ease((t - 0.6) / 0.5)
    if p:
        rect(im, (LOG_X, 330, 1816, 1000), mix(BG, CARD, p), mix(BG, RULE, p), 2, 18)
        txt(im, LOG_X + 28, 352, "ON THE SERVER", 22, MUTED, "mono", opacity=p)
        txt(im, 1788, 352, "POST /mcp/", 22, MUTED, "mono", "right", p)
    y = 404
    for i, (at, kind, value) in enumerate(LOG):
        q = ease((t - at) / 0.35)
        if q <= 0:
            break
        if kind == "call" and i:
            y += 18
        color = {"call": VIOLET, "ok": MINT, "log": AMBER}[kind]
        draw(im).ellipse((LOG_X + 28, y + 9, LOG_X + 38, y + 19), fill=mix(CARD, color, q))
        for piece in wrap_mono(value, 19, 1816 - LOG_X - 90):
            txt(im, LOG_X + 54, y, piece, 19, color if kind == "call" else INK, "mono", opacity=q)
            y += 28
        y += 6
    txt(
        im,
        960,
        1030,
        "Every call is checked against the token's user. Every write lands in Django's LogEntry, readable by you too.",
        22,
        MUTED,
        "regular",
        "center",
        ease((t - 10.6) / 0.5),
    )
    return im


def wrap_mono(value, size, width):
    lines, current = [], ""
    for word in value.split(" "):
        trial = (current + " " + word).strip() if current else word
        if current and width_of(trial, size, "mono") > width:
            lines.append(current)
            current = "    " + word
        else:
            current = trial
    return lines + [current] if current else lines


# 6 · Get started -------------------------------------------------------------

STEPS = (
    (
        "Install.",
        "Add the app, mount the endpoint, migrate.",
        (
            "pip install django-admin-mcp",
            "INSTALLED_APPS += ['django_admin_mcp']",
            "urlpatterns += [path('mcp/',",
            "    include('django_admin_mcp.urls'))]",
            "python manage.py migrate django_admin_mcp",
        ),
    ),
    (
        "Expose a model.",
        "Set the flag on the ModelAdmin, then create a token in the admin.",
        (
            "class ArticleAdmin(MCPAdminMixin,",
            "                   admin.ModelAdmin):",
            "    mcp_expose = True",
        ),
    ),
    (
        "Point your client at it.",
        "Any MCP client over HTTP, for example a .mcp.json for Claude Code.",
        (
            '"url": "http://localhost:8000/mcp/",',
            '"headers": {',
            '  "Authorization": "Bearer mcp_7Qf3kA2b.…"',
            "}",
        ),
    ),
)


def get_started(t):
    im = base(t + STARTS[5])
    title(im, "Install. Expose. Connect.", t, "Three steps from a Django project to an MCP server.")
    for i, (label, detail, code) in enumerate(STEPS):
        x = 100 + i * 572
        p = ease((t - 0.4 - i * 0.45) / 0.6)
        if p <= 0:
            continue
        y = 360 + 24 * (1 - p)
        rect(im, (x, y, x + 556, y + 500), mix(BG, CARD, p), mix(BG, RULE, p), 2, 22)
        draw(im).ellipse((x + 32, y + 32, x + 84, y + 84), fill=mix(CARD, GREEN, p))
        txt(im, x + 58, y + 40, str(i + 1), 32, BG, "bold", "center", p)
        txt(im, x + 104, y + 38, label, 40, INK, "bold", opacity=p)
        for n, piece in enumerate(wrap(detail, 26, 470)):
            txt(im, x + 36, y + 116 + n * 34, piece, 26, MUTED, opacity=p)
        for n, value in enumerate(code):
            q = ease((t - 0.9 - i * 0.45 - n * 0.2) / 0.4)
            txt(im, x + 36, y + 216 + n * 42, value, 19, MINT if n == 0 or i else INK, "mono", opacity=q)
    foot(
        im,
        "Docs: 7tg.github.io/django-admin-mcp  ·  GET /mcp/health/ for health checks  ·  JSON-RPC 2.0 over HTTP",
    )
    return im


def wrap(value, size, width, weight="regular"):
    lines, current = [], ""
    for word in value.split():
        trial = (current + " " + word).strip()
        if current and width_of(trial, size, weight) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + [current] if current else lines


# 7 · Ending ------------------------------------------------------------------


def ending(t):
    im = base(t + STARTS[6])
    p = ease((t - 0.1) / 0.7)
    wordmark = width_of("django-admin-mcp", 132, "bold")
    left = (W - (130 + 44 + wordmark)) / 2
    mark(im, left, 240 + 20 * (1 - p), 130, p)
    reveal(im, left + 174, 226, "django-admin-mcp", 132, t, at=0.15)
    reveal(
        im,
        960,
        400,
        "YOUR ADMIN  ·  YOUR PERMISSIONS  ·  ANY MCP CLIENT",
        28,
        t,
        at=0.35,
        color=GREEN,
        weight="mono",
        align="center",
    )
    reveal(
        im,
        960,
        456,
        "Add a mixin. The agent gets the operations you designed, nothing more.",
        40,
        t,
        at=0.45,
        color=INK,
        weight="semibold",
        align="center",
    )
    q = ease((t - 0.9) / 0.5)
    if q:
        w = width_of("pip install django-admin-mcp", 48, "monobold") + 80
        rect(
            im,
            (960 - w / 2, 560 + 16 * (1 - q), 960 + w / 2, 650 + 16 * (1 - q)),
            mix(BG, CARD, q),
            mix(BG, GREEN, q),
            2,
            18,
        )
        txt(im, 960, 582 + 16 * (1 - q), "pip install django-admin-mcp", 48, MINT, "monobold", "center", q)
    reveal(im, 960, 740, "github.com/7tg/django-admin-mcp", 52, t, at=1.4, weight="bold", align="center")
    txt(
        im,
        960,
        840,
        "MIT licensed. If it saved you time, a star helps others find it.",
        30,
        MUTED,
        "regular",
        "center",
        ease((t - 1.9) / 0.6),
    )
    return im


# Assembly ----------------------------------------------------------------------

SCENES = (hook, mixin, through, token, ask, get_started, ending)


def scene_at(t):
    index = next((i for i, end in enumerate(ENDS) if t < end), len(ENDS) - 1)
    return index, t - STARTS[index]


def frame(t):
    index, local = scene_at(t)
    im = SCENES[index](local)
    if index and local < WIPE:
        old = SCENES[index - 1](ENDS[index - 1] - STARTS[index - 1] - 0.001)
        p = smooth(local / WIPE)
        lean = 260
        edge = -lean - 60 + (W + 2 * lean + 120) * p
        mask = Image.new("L", (W, H), 0)
        draw(mask).polygon([(-10, 0), (edge + lean, 0), (edge, H), (-10, H)], fill=255)
        im = Image.composite(im, old, mask)
        d = draw(im)
        d.polygon([(edge + lean, 0), (edge + lean + 46, 0), (edge + 46, H), (edge, H)], fill=GREEN)
        d.polygon([(edge + lean + 46, 0), (edge + lean + 58, 0), (edge + 58, H), (edge + 46, H)], fill=VIOLET)
    chrome(im, index, t)
    return im


def frame_bytes(n):
    return frame(n / FPS).tobytes()


def storyboard(destination):
    times = tuple(t for start, end in zip(STARTS, ENDS, strict=True) for t in (start + 1.2, end - 0.6))
    rows = math.ceil(len(times) / 4)
    sheet = Image.new("RGB", (1920, rows * 300), BG)
    for i, t in enumerate(times):
        tile = frame(t).resize((480, 270), Image.Resampling.LANCZOS)
        x, y = i % 4 * 480, i // 4 * 300
        sheet.paste(tile, (x, y))
        txt(sheet, x + 10, y + 272, f"{t:04.1f}s", 20, MUTED, "mono")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, quality=88)
    print(f"Wrote {destination}", flush=True)


def ffmpeg_path():
    path = shutil.which("ffmpeg")
    if not path:
        raise SystemExit("FFmpeg is required.")
    return path


def encode_film(destination, audio, fps, workers):
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y"]
    cmd += [
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{W}x{H}",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
    ]
    if audio:
        cmd += ["-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += ["-vf", "scale=out_color_matrix=bt709:out_range=tv", "-c:v", "libx264", "-preset", "medium", "-crf", "19"]
    cmd += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-color_primaries", "bt709", "-color_trc", "bt709"]
    cmd += ["-colorspace", "bt709", "-color_range", "tv", "-t", str(DURATION), str(destination)]
    total = DURATION * fps
    global FPS
    FPS = fps
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc, Pool(workers) as pool:
        try:
            for n, data in enumerate(pool.imap(frame_bytes, range(total), chunksize=8)):
                proc.stdin.write(data)
                if n % (fps * 5) == 0:
                    print(f"Rendered {n // fps}/{DURATION}s", flush=True)
        finally:
            proc.stdin.close()
        if proc.wait():
            raise RuntimeError("FFmpeg encoding failed")
    print(f"Wrote {destination}", flush=True)


def encode_gif(source, destination, width=960, fps=12, colors=96):
    destination.parent.mkdir(parents=True, exist_ok=True)
    base_cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y"]
    scale = f"fps={fps},scale={width}:-2:flags=lanczos"
    with tempfile.TemporaryDirectory(prefix="django-admin-mcp-gif-") as directory:
        palette = str(Path(directory) / "palette.png")
        subprocess.run(
            base_cmd
            + [
                "-i",
                str(source),
                "-vf",
                f"{scale},palettegen=max_colors={colors}:stats_mode=diff",
                "-frames:v",
                "1",
                palette,
            ],
            check=True,
        )
        subprocess.run(
            base_cmd
            + [
                "-i",
                str(source),
                "-i",
                palette,
                "-filter_complex",
                f"[0:v]{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
            ]
            + ["-loop", "0", str(destination)],
            check=True,
        )
    size = destination.stat().st_size
    if size >= 10_000_000:
        raise RuntimeError(f"{destination} is {size / 1e6:.1f} MB, over the 10 MB preview limit")
    print(f"Wrote {destination} ({size / 1e6:.1f} MB)", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output", type=Path, help="film (.mp4), or a still with --frame")
    p.add_argument("--frame", type=float, help="render one frame at this second as an image")
    p.add_argument("--storyboard", type=Path, help="write a contact sheet of every chapter")
    p.add_argument("--gif-from", type=Path, help="only rebuild the GIF preview from this film")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--fps", type=int, default=FPS)
    p.add_argument("--workers", type=int, default=None)
    args = p.parse_args()
    if args.storyboard:
        storyboard(args.storyboard)
    if args.gif_from:
        encode_gif(args.gif_from, (args.output or args.gif_from).with_suffix(".gif"))
    elif args.output and args.frame is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frame(args.frame).save(args.output)
        print(f"Wrote {args.output}", flush=True)
    elif args.output:
        with tempfile.TemporaryDirectory(prefix="django-admin-mcp-film-") as directory:
            audio = None
            if not args.no_audio:
                audio = Path(directory) / "score.wav"
                score = Path(__file__).resolve().with_name("demo_audio.py")
                subprocess.run(
                    [sys.executable, str(score), "--output", str(audio), "--duration", str(DURATION)], check=True
                )
            encode_film(args.output, audio, args.fps, args.workers)
        encode_gif(args.output, args.output.with_suffix(".gif"))
    elif not args.storyboard:
        p.error("Use --output, --storyboard or --gif-from.")


if __name__ == "__main__":
    main()
