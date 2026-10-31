"""Render the README's cumulative PyPI downloads chart in star-history's xkcd style.

pypistats only serves the last 180 days, so daily counts are accumulated in
docs/media/downloads.json and the chart is drawn from that history.
"""

import base64
import json
import urllib.request
from datetime import date, timedelta
from pathlib import Path

PACKAGE = "django-admin-mcp"
HERE = Path(__file__).resolve().parent
MEDIA = HERE.parent / "docs" / "media"
HISTORY = MEDIA / "downloads.json"
CHART = MEDIA / "downloads.svg"
FONT = HERE / "xkcd.woff"

W, H = 800, 533.333
PW, PH = 700, 423.333
COLOR = "#dd4528"
TICK = "font-family:xkcd;font-size:16px;fill:#000"


def fetch():
    url = f"https://pypistats.org/api/packages/{PACKAGE}/overall?mirrors=false"
    req = urllib.request.Request(url, headers={"User-Agent": f"{PACKAGE}-readme-chart"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        rows = json.load(resp)["data"]
    return {r["date"]: r["downloads"] for r in rows if r["category"] == "without_mirrors"}


def render(history):
    days = sorted(history)
    start, end = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    span = max((end - start).days, 1)

    cumulative, total = {}, 0
    for d in days:
        total += history[d]
        cumulative[date.fromisoformat(d)] = total
    # Weekly samples keep the line smooth, like star-history's sparse points.
    points, running, day = [(0, 0)], 0, start
    while day <= end:
        running = cumulative.get(day, running)
        if (day - start).days % 7 == 6 or day == end:
            points.append(((day - start).days, running))
        day += timedelta(days=1)

    step = next(m * 10**e for e in range(10) for m in (1, 2, 5) if total / (m * 10**e) <= 6)
    y_max = -(-total // step) * step

    def x(offset):
        return PW * offset / span

    def y(value):
        return PH * (1 - value / y_max)

    line = "M" + " L".join(f"{x(d):.3f} {y(v):.3f}" for d, v in points)
    font = base64.b64encode(FONT.read_bytes()).decode()

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        'style="stroke-width:3;font-family:xkcd;background:#fff">',
        '<defs><style>@font-face{font-family:"xkcd";'
        f'src:url(data:application/font-woff;charset=utf-8;base64,{font})format("woff")}}</style></defs>',
        '<filter id="xkcdify" width="100%" height="100%" x="-5" y="-5" filterUnits="userSpaceOnUse">'
        '<feTurbulence baseFrequency=".05" result="noise" type="fractalNoise"/>'
        '<feDisplacementMap in="SourceGraphic" in2="noise" scale="5" xChannelSelector="R" yChannelSelector="G"/>'
        "</filter>",
        f'<rect width="{W}" height="{H}" fill="#fff"/>',
        '<g transform="translate(70 60)">',
        f'<path fill="none" d="M.5.5h{PW}" filter="url(#xkcdify)" style="stroke:#000" transform="translate(0 {PH})"/>',
    ]
    month = date(start.year, start.month, 1)
    while month <= end:
        if month >= start:
            parts.append(
                f'<text y="6" dy=".71em" text-anchor="middle" style="{TICK}" '
                f'transform="translate({x((month - start).days):.3f} {PH})">{month.strftime("%B")}</text>'
            )
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    parts.append(f'<path fill="none" d="M-1 {PH + 0.5}H.5V.5H-1" filter="url(#xkcdify)" style="stroke:#000"/>')
    for v in range(step, y_max + 1, step):
        label = f"{v / 1000:g}k" if v >= 1000 else str(v)
        parts.append(
            f'<text x="-7" dy=".32em" text-anchor="end" style="{TICK}" '
            f'transform="translate(0 {y(v):.3f})">{label}</text>'
        )
    legend_w = 21 + 8.6 * len(PACKAGE) + 12
    parts += [
        f'<path fill="none" stroke="{COLOR}" d="{line}" filter="url(#xkcdify)"/>',
        f'<rect width="{legend_w:.0f}" height="32" fill-opacity=".85" stroke="#000" stroke-width="2" '
        'filter="url(#xkcdify)" rx="5" ry="5" style="fill:#fff" transform="translate(8 5)"/>',
        '<g transform="translate(8 5)">',
        f'<rect width="8" height="8" x="7" y="12" filter="url(#xkcdify)" rx="2" ry="2" style="fill:{COLOR}"/>',
        f'<text x="21" y="20" style="font-size:15px;fill:#000">{PACKAGE}</text>',
        "</g>",
        f'<text x="{PW}" y="{PH - 12}" text-anchor="end" style="font-size:16px;fill:#666">{total:,} total</text>',
        "</g>",
        '<text x="50%" y="30" text-anchor="middle" style="font-size:20px;font-weight:700;fill:#000">'
        "Download History</text>",
        f'<text x="50%" y="{H - 10}" text-anchor="middle" style="font-size:17px;fill:#000">Date</text>',
        '<text x="-217" y="14" dy=".75em" text-anchor="end" transform="rotate(-90)" '
        'style="font-size:17px;fill:#000">PyPI Downloads</text>',
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main():
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    history.update(fetch())
    history = dict(sorted(history.items()))
    HISTORY.write_text(json.dumps(history, indent=1) + "\n")
    CHART.write_text(render(history))


if __name__ == "__main__":
    main()
