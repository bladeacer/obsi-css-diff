import difflib
import json
import re
import shutil
from pathlib import Path

import docker
import feedparser
import typer
from docker.client import DockerClient
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

# Configuration
CHANGELOG_URL: str = "https://obsidian.md/changelog.xml"
IMAGE_NAME: str = "lscr.io/linuxserver/obsidian"
CACHE_FILE: Path = Path(".obsidian_cache.json")
CSS_DIR: Path = Path("extracted_css")

app = typer.Typer(
    help="obsi-css-diff: A utility to extract and compare Obsidian CSS from Docker images.",
    add_completion=False,
    no_args_is_help=True,
)
console: Console = Console()


def get_docker() -> DockerClient:
    try:
        return docker.from_env()
    except Exception as e:
        console.print("[red]Error:[/red] Docker is not running. Please start Docker to extract CSS.")
        raise typer.Exit(1) from e


def get_versions(force_refresh: bool = False, include_beta: bool = False) -> list[dict]:
    """Parses Atom feed. Filters beta releases (< 1.0.0) by default."""
    if not force_refresh and CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except json.JSONDecodeError:
            pass

    console.print("[bold blue]Refreshing Obsidian Version Cache...[/bold blue]")
    feed = feedparser.parse(CHANGELOG_URL)

    if feed.bozo:
        console.print("[red]Error:[/red] Failed to parse feed. Check your internet connection.")
        raise typer.Exit(1)

    versions: list[dict] = []
    for entry in feed.entries:
        title = entry.title
        # Regex for version number
        match = re.search(r"v?(\d+\.\d+\.?\d*)", title)
        if match:
            v_num = match.group(1)

            # Beta filtering (pre 1.0.0)
            major_v = int(v_num.split(".")[0])
            if not include_beta and major_v < 1:
                continue

            v_type = "Desktop" if "Desktop" in title else "Mobile"
            is_public = "(Public)" in title

            versions.append({"type": v_type, "version": v_num, "title": title, "public": is_public})

    if not versions:
        console.print("[red]Error:[/red] No versions found matching criteria.")
        raise typer.Exit(1)

    CACHE_FILE.write_text(json.dumps(versions, indent=2))
    return versions


def display_table(versions: list[dict], title: str):
    """Beautified table display with color-coded status."""
    table = Table(title=title, header_style="bold magenta", box=None, padding=(0, 2))
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Type", width=10)
    table.add_column("Version", style="green")
    table.add_column("Status")

    for idx, v in enumerate(versions):
        status = "[cyan]Public[/cyan]" if v["public"] else "[yellow]Early Access[/yellow]"
        table.add_row(str(idx), v["type"], v["version"], status)

    console.print(table)


def extract_css_file(client: DockerClient, version: str) -> Path:
    CSS_DIR.mkdir(exist_ok=True)
    local_path = CSS_DIR / f"obsidian_{version}.css"

    if local_path.exists():
        return local_path

    full_image = f"{IMAGE_NAME}:{version}"
    console.print(f"  [yellow]→[/yellow] Pulling/Extracting {full_image}...")

    try:
        client.images.pull(IMAGE_NAME, tag=version)
        # Directly cat the file to avoid mounting/tar overhead
        find_cmd = "find / -name app.css"
        remote_path = client.containers.run(full_image, find_cmd, remove=True).decode().strip().split("\n")[0]

        if not remote_path:
            raise FileNotFoundError("app.css not found in container")

        content = client.containers.run(full_image, f"cat {remote_path}", remove=True)
        local_path.write_bytes(content)
        return local_path
    except Exception as e:
        console.print(f"  [red]Failed extraction for {version}:[/red] {e}")
        return None


@app.command()
def interactive(
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh the version cache."),
    beta: bool = typer.Option(False, "--beta", "-b", help="Include legacy beta releases (< 1.0.0)."),
):
    """
    Interactive workflow to:
    1. List releases
    2. Filter by platform
    3. Select multiple IDs for CSS extraction
    4. Compare changes
    """
    all_versions = get_versions(force_refresh=force, include_beta=beta)

    # 1. Show all
    display_table(all_versions, "Available Obsidian Releases")

    # 2. Filter
    filter_choice = Prompt.ask("Filter results? [d]esktop, [m]obile, [a]ll", choices=["d", "m", "a"], default="a")

    filtered = all_versions
    if filter_choice == "d":
        filtered = [v for v in all_versions if v["type"] == "Desktop"]
    elif filter_choice == "m":
        filtered = [v for v in all_versions if v["type"] == "Mobile"]

    if filter_choice != "a":
        display_table(filtered, f"Filtered: {('Desktop' if filter_choice == 'd' else 'Mobile')}")

    # 3. Extraction Selection with Input Validation
    selection = Prompt.ask("\nEnter IDs to extract (e.g., '0,2') or 'latest'", default="latest")

    indices: list[int] = []
    if selection.lower() == "latest":
        indices = [0]
    else:
        # Regex to handle spaces, commas, or multiple digits safely
        raw_indices = re.split(r"[,\s]+", selection.strip())
        for i in raw_indices:
            if i.isdigit():
                idx = int(i)
                if 0 <= idx < len(filtered):
                    indices.append(idx)
                else:
                    console.print(f"[red]Warning:[/red] ID {idx} is out of range. Skipping.")
            elif i:
                console.print(f"[red]Warning:[/red] '{i}' is not a valid ID. Skipping.")

    if not indices:
        console.print("[red]No valid IDs selected. Exiting.[/red]")
        return

    client = get_docker()
    paths: list[Path] = []

    for idx in indices:
        v = filtered[idx]
        p = extract_css_file(client, v["version"])
        if p:
            paths.append(p)

    # 4. Diff logic
    if len(paths) >= 2:
        if Prompt.confirm("\nShow diff between the first two selected?", default=True):
            show_diff(paths[0], paths[1])
    elif len(paths) == 1:
        console.print(f"\n[green]Done![/green] File saved to: {paths[0]}")


def show_diff(path_a: Path, path_b: Path):
    """Side-by-side terminal diff."""
    lines_a = path_a.read_text().splitlines()
    lines_b = path_b.read_text().splitlines()

    diff = difflib.unified_diff(lines_a, lines_b, fromfile=path_a.name, tofile=path_b.name, lineterm="")

    console.print(Panel(f"Comparing {path_a.name} vs {path_b.name}", border_style="cyan"))

    has_diff = False
    for line in diff:
        has_diff = True
        color = (
            "green"
            if line.startswith("+")
            else "red"
            if line.startswith("-")
            else "blue"
            if line.startswith("@@")
            else "dim"
        )
        console.print(line, style=color)

    if not has_diff:
        console.print("[yellow]No CSS changes found between these versions.[/yellow]")


@app.command()
def clean():
    """Wipe cache and extracted CSS files."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    if CSS_DIR.exists():
        shutil.rmtree(CSS_DIR)
    console.print("[green]Environment cleaned successfully.[/green]")


if __name__ == "__main__":
    app()
