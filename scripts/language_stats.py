import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER = "Fabrizio-HM"
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = Path("dist/languages.svg")
COLORS = ["#b48ead", "#569cd6", "#e5c07b", "#98c379", "#d19a66", "#56b6c2"]


def get(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Fabrizio-HM-profile-stats", "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_svg(counts):
    items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    if len(items) > 6:
        items = items[:5] + [("Other", sum(n for _, n in items[5:]))]
    total = sum(n for _, n in items)
    title = 'Top Languages by Repo'
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="450" height="175" viewBox="0 0 450 175" role="img" aria-label="GitHub languages by code size">',
           '<rect width="450" height="175" rx="10" fill="#1a1b27"/>',
           f'<text x="18" y="30" fill="#70a5fd" font-size="16" font-family="Arial,sans-serif">{title}</text>']
    if total == 0:
        svg.append('<text x="18" y="90" fill="#a9b1d6" font-size="13" font-family="Arial,sans-serif">No public language data available</text>')
    else:
        cx, cy, radius, stroke = 100, 105, 46, 21
        circumference = 2 * math.pi * radius
        svg.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#292e42" stroke-width="{stroke}"/>')
        offset = 0
        for i, (lang, val) in enumerate(items):
            length = (val / total) * circumference
            svg.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{COLORS[i]}" stroke-width="{stroke}" stroke-dasharray="{length:.3f} {circumference-length:.3f}" stroke-dashoffset="{-offset:.3f}" transform="rotate(-90 {cx} {cy})"/>')
            offset += length
            y = 59 + 21 * i
            svg.append(f'<circle cx="203" cy="{y-4}" r="5" fill="{COLORS[i]}"/>')
            svg.append(f'<text x="216" y="{y}" fill="#c0caf5" font-size="12" font-family="Arial,sans-serif">{esc(lang)} — {100*val/total:.1f}%</text>')
        svg.append('<text x="18" y="166" fill="#8590ad" font-size="9" font-family="Arial,sans-serif">Public GitHub repositories · language bytes, not skill level</text>')
    svg.append('</svg>')
    return '\n'.join(svg) + '\n'


def main():
    counts = {}
    repos = []
    page = 1
    while True:
        batch = get(f"{API}/users/{USER}/repos?per_page=100&page={page}&type=owner")
        repos.extend(repo for repo in batch if not repo.get("fork") and not repo.get("archived"))
        if len(batch) < 100:
            break
        page += 1
    for repo in repos:
        languages = get(f"{API}/repos/{repo['full_name']}/languages")
        for lang, size in languages.items():
            counts[lang] = counts.get(lang, 0) + size
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_svg(counts), encoding="utf-8")
    print(f"Language chart: {len(repos)} public repos, {len(counts)} languages; {OUT}")


if __name__ == "__main__":
    main()
