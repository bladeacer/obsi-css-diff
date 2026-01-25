import json
from pathlib import Path

import requests
from rich.console import Console

console = Console()


class ElectronSource:
    RAW_URL = "https://raw.githubusercontent.com/Kilian/electron-to-chromium/master/full-versions.json"
    CACHE_DIR = Path(".obsidian_cache")
    CACHE_FILE = CACHE_DIR / "electron_versions.json"

    def __init__(self):
        self.CACHE_DIR.mkdir(exist_ok=True)

    def get_data(self, force: bool = False) -> dict:
        """
        Fetches Electron-to-Chromium mappings.
        Returns a dict: {"electron_version": "chromium_version"}
        """
        if not force and self.CACHE_FILE.exists():
            try:
                return json.loads(self.CACHE_FILE.read_text())
            except json.JSONDecodeError:
                pass

        console.print("[bold magenta]Fetching Electron-to-Chromium Mappings...[/bold magenta]")

        try:
            response = requests.get(self.RAW_URL, timeout=10)
            response.raise_for_status()
            data = response.json()

            self.CACHE_FILE.write_text(json.dumps(data, indent=2))
            return data

        except Exception as e:
            console.print(f"[red]Electron Mapping Error:[/red] {e}")
            return {}

    def map_version(self, electron_version: str, mapping_data: dict = None) -> str:
        """Helper to find a specific chromium version for a given electron version."""
        if mapping_data is None:
            mapping_data = self.get_data()

        return mapping_data.get(electron_version, "Unknown")
