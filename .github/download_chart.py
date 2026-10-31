"""Render the README's cumulative PyPI downloads chart.

pypistats only serves the last 180 days, so daily counts are accumulated in
docs/media/downloads.json and the chart is drawn from that history.
"""

import json
import urllib.request
from datetime import date
from pathlib import Path

PACKAGE = "django-admin-mcp"
MEDIA = Path(__file__).resolve().parent.parent / "docs" / "media"
HISTORY = MEDIA / "downloads.json"
CHART = MEDIA / "downloads.svg"

W, H = 800, 533
LEFT, RIGHT, TOP, BOTTOM = 80, 30, 70, 60


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
    points, total = [], 0
    for d in days:
        total += history[d]
        points.append(((date.fromisoformat(d) - start).days, total))

    step = next(m * 10**e for e in range(10) for m in (1, 2, 5) if total / (m * 10**e) <= 6)
    y_max = -(-total // step) * step

    pw, ph = W - LEFT - RIGHT, H - TOP - BOTTOM

    def xy(day, value):
        return LEFT + pw * day / span, TOP + ph * (1 - value / y_max)

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(d, v) for d, v in points))
    area = f"{LEFT},{TOP + ph} {line} {LEFT + pw},{TOP + ph}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#fff"/>',
        f'<text x="{W / 2}" y="38" text-anchor="middle" font-size="20" font-weight="600" fill="#333">'
        "PyPI Download History</text>",
    ]
    for v in range(0, y_max + 1, step):
        _, y = xy(0, v)
        parts.append(f'<line x1="{LEFT}" x2="{LEFT + pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eee"/>')
        label = f"{v / 1000:g}k" if v >= 1000 else str(v)
        parts.append(
            f'<text x="{LEFT - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="13" fill="#666">{label}</text>'
        )
    month = date(start.year, start.month, 1)
    while month <= end:
        if month >= start:
            x, _ = xy((month - start).days, 0)
            parts.append(
                f'<text x="{x:.1f}" y="{TOP + ph + 24}" text-anchor="middle" font-size="13" fill="#666">'
                f'{month.strftime("%b %Y")}</text>'
            )
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    parts += [
        f'<line x1="{LEFT}" x2="{LEFT + pw}" y1="{TOP + ph}" y2="{TOP + ph}" stroke="#999"/>',
        f'<polygon points="{area}" fill="#3775a9" fill-opacity="0.12"/>',
        f'<polyline points="{line}" fill="none" stroke="#3775a9" stroke-width="2.5" stroke-linejoin="round"/>',
        f'<text x="{LEFT + 12}" y="{TOP + 20}" font-size="14" fill="#333">'
        f"{total:,} downloads since {start.strftime('%b %-d, %Y')}</text>",
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
