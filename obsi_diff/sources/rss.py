import json
import re
from pathlib import Path

import feedparser
import requests
from rich.console import Console

console = Console()


class RSSSource:
    CHANGELOG_URL = "https://obsidian.md/changelog.xml"
    CACHE_DIR = Path(".obsidian_cache")
    CACHE_FILE = CACHE_DIR / "rss_versions.json"

    def __init__(self):
        self.CACHE_DIR.mkdir(exist_ok=True, parents=True)

    def get_data(self, force: bool = False) -> list[dict]:
        if not force and self.CACHE_FILE.exists():
            try:
                return json.loads(self.CACHE_FILE.read_text())
            except (OSError, json.JSONDecodeError):
                pass

        try:
            response = requests.get(self.CHANGELOG_URL, timeout=10)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception as e:
            console.print(f"[red]RSS Fetch Error:[/red] {e}")
            return []

        versions = []
        for entry in feed.entries:
            title = entry.get("title", "")
            v_match = re.search(r"(\d+\.\d+\.\d+)", title)
            if not v_match:
                continue

            v_num = v_match.group(1)
            content = entry.get("content", [{}])[0].get("value", "")
            el_match = re.search(r"Electron v?(\d+\.\d+\.\d+)", content, re.IGNORECASE)

            versions.append(
                {
                    "version": v_num,
                    "type": "Desktop" if "Desktop" in title else "Mobile",
                    "date": entry.get("updated", entry.get("published", "---")),
                    "electron": el_match.group(1) if el_match else None,
                    "title": title,
                    "source": "rss",
                }
            )

        # Sort to fill Electron versions backwards through time
        versions.sort(key=lambda x: [int(p) for p in re.findall(r"\d+", x["version"])])

        last_electron = "13.0.0"
        for v in versions:
            if v["electron"]:
                last_electron = v["electron"]
            else:
                v["electron"] = last_electron

        versions.reverse()
        self.CACHE_FILE.write_text(json.dumps(versions, indent=2))
        return versions
