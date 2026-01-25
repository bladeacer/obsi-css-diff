from pathlib import Path
from shutil import rmtree

import typer
from rich.console import Console

from obsi_diff.cli import run_tui

app = typer.Typer(help="obsi-css-diff: TUI-based Obsidian version tracking and CSS diffing.", add_completion=False)
console = Console()


@app.command()
def interact(refresh: bool = typer.Option(False, "--refresh", "-r", help="Force refresh metadata cache")):
    """Launch the interactive TUI to select an Obsidian version."""
    # Control passes to Textual
    result = run_tui(refresh)

    # 1. Handle explicit exit/abort
    if not result:
        console.print("\n[yellow]⚠ Selection cancelled by user.[/yellow]")
        return

    # 2. Handle internal TUI errors
    if isinstance(result, str) and result.startswith("Error"):
        console.print(f"\n[bold red]✖ TUI Error:[/bold red] {result}")
        raise typer.Exit(1)

    # 3. Success Flow: Handle the selected version
    console.print("\n[bold green]✓ Version Selected and Confirmed[/bold green]")
    console.print("─" * 30)
    console.print(f"  [b]Obsidian Version:[/]  [cyan]{result['version']}[/]")
    console.print(f"  [b]Docker Tag:[/]        [magenta]{result['tag']}[/]")
    console.print("─" * 30)

    # This is where the next module (DockerManager) will be called.
    console.print("\n[dim]Initializing extraction process...[/dim]")


@app.command()
def clean():
    """Wipe all cached metadata."""
    cache_dir = Path(".obsidian_cache")
    if cache_dir.exists():
        rmtree(cache_dir)
        console.print("[green]✓[/green] Local metadata cache cleared.")
    else:
        console.print("[dim]Cache is already empty.[/dim]")


if __name__ == "__main__":
    app()
