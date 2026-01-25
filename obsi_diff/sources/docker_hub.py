import json
import re
from pathlib import Path

import requests
from rich.console import Console

console = Console()


class DockerSource:
    API_URL = "https://hub.docker.com/v2/repositories/linuxserver/obsidian/tags"
    CACHE_DIR = Path(".obsidian_cache")
    CACHE_FILE = CACHE_DIR / "docker_versions.json"

    def __init__(self):
        self.CACHE_DIR.mkdir(exist_ok=True)

    def get_data(self, force: bool = False, progress=None, task_id=None) -> list[dict]:
        if not force and self.CACHE_FILE.exists():
            try:
                return json.loads(self.CACHE_FILE.read_text())
            except (OSError, json.JSONDecodeError):
                pass

        versions = []
        url = self.API_URL
        params = {"page_size": 100}

        try:
            while url:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                if progress and task_id and params:
                    total_items = data.get("count", 0)
                    progress.update(task_id, total=total_items)
                    params = None

                for result in data.get("results", []):
                    tag_name = result["name"]
                    noise = ["latest", "develop", "amd64", "arm64", "-ls"]
                    if any(x in tag_name for x in noise):
                        continue

                    clean_version = tag_name.replace("version-", "").split("-")[0]

                    # Regex check for numeric versions to filter out "Unknown"
                    v_parts = re.findall(r"\d+", clean_version)
                    if not v_parts or int(v_parts[0]) < 1:
                        continue

                    if progress and task_id:
                        progress.advance(task_id)

                    versions.append(
                        {
                            "version": clean_version,
                            "tag": tag_name,
                            "last_updated": result.get("last_updated"),
                            "source": "docker",
                        }
                    )

                url = data.get("next")

        except Exception as e:
            console.print(f"[red]Docker Hub API Error:[/red] {e}")
            return []

        if versions:
            versions.sort(key=lambda x: x["last_updated"] or "", reverse=True)
            self.CACHE_FILE.write_text(json.dumps(versions, indent=2))

        return versions
