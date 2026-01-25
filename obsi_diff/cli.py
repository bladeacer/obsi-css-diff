import re

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Middle, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, LoadingIndicator, Static

from obsi_diff.sources.docker_hub import DockerSource
from obsi_diff.sources.electron import ElectronSource
from obsi_diff.sources.rss import RSSSource


class ConfirmScreen(ModalScreen[bool]):
    def __init__(self, version: str):
        super().__init__()
        self.version = version

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(f"Proceed with Obsidian [b cyan]v{self.version}[/b cyan]?", id="confirm-msg")
            with Horizontal():
                yield Button("Yes (Enter)", variant="success", id="yes")
                yield Button("No (Esc)", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def on_key(self, event) -> None:
        if event.key == "enter":
            self.dismiss(True)
        elif event.key == "escape":
            self.dismiss(False)


class LoadingScreen(Screen):
    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Static("[bold blue]Syncing Obsidian Release Data...[/]", id="loading-text")
                yield LoadingIndicator()


class ObsiVerPicker(App):
    CSS = """
    DataTable { height: 1fr; border: solid gray; margin: 0 1; }
    DataTable:focus { border: double cyan; }
    #search-container { dock: bottom; padding: 0 1; display: none; height: 3; }
    #search-container.-visible { display: block; }
    #search-input { border: tall gray; background: $accent-darken-3; }
    #mode-bar { height: 1; background: $panel; padding: 0 1; color: white; }
    .mode-normal { background: $success-darken-1; }
    .mode-search { background: $warning-darken-1; }
    #confirm-dialog { width: 44; height: 11; background: $panel; border: thick $primary;
                      padding: 1; align: center middle; }
    #confirm-msg { margin-bottom: 1; text-align: center; }
    #confirm-dialog Horizontal { align: center middle; }
    #confirm-dialog Button#yes { margin-right: 2; }
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("n", "next_match", "Next Match"),
        Binding("N", "prev_match", "Prev Match"),
        Binding("/", "toggle_search", "Search"),
        Binding("escape", "cancel_search", "Normal Mode", show=False),
        Binding("m", "toggle_mobile", "Mobile"),
        Binding("e", "toggle_early", "Early"),
        Binding("f", "toggle_found", "Docker"),
        Binding("s", "toggle_sort", "Sort"),
        Binding("enter", "submit", "Select"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, force_refresh: bool = False):
        super().__init__()
        self.force_refresh = force_refresh
        self.raw_data = {}
        self.search_query = ""
        self.show_mobile = True
        self.show_early_access = True
        self.found_only = False
        self.sort_by_priority = True

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row")
        with Vertical(id="search-container"):
            yield Input(placeholder="Search...", id="search-input")
        yield Static(id="mode-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self.push_screen(LoadingScreen())
        self.fetch_all_data()

    @work(exclusive=True, thread=True)
    def fetch_all_data(self) -> None:
        try:
            data = {
                "rss": RSSSource().get_data(force=self.force_refresh),
                "docker": DockerSource().get_data(force=self.force_refresh),
                "electron": ElectronSource().get_data(force=self.force_refresh),
            }
            self.call_from_thread(self.handle_data_loaded, data)
        except Exception as e:
            self.exit(result=f"Error: {e}")

    def handle_data_loaded(self, data: dict) -> None:
        self.raw_data = data
        if self.screen_stack:
            self.pop_screen()
        table = self.query_one(DataTable)
        if not table.columns:
            table.add_columns("ID", "Version", "Type", "Released", "Docker Status", "Electron", "Chromium")
        self.update_table()
        table.focus()

    def update_table(self) -> None:
        if not self.raw_data:
            return
        table = self.query_one(DataTable)
        table.clear(columns=False)
        docker_map = {v["version"]: v for v in self.raw_data.get("docker", []) if "version" in v}
        electron_map = self.raw_data.get("electron", {})

        filtered = []
        seen = set()
        for rss in self.raw_data.get("rss", []):
            v, t = rss.get("version", "0.0.0"), rss.get("type", "Desktop")
            el_v = rss.get("electron", "---")
            cr_v = electron_map.get(el_v, "---")

            is_early = any(x in rss.get("title", "") for x in ["(Early access)", "(Insider)"])
            has_d = v in docker_map and t == "Desktop"
            stat = "Found" if has_d else ("Missing" if t == "Desktop" else "N/A")
            searchable_text = f"{v} {t} {stat} {rss.get('date')} {el_v} {cr_v}".lower()

            # Filtering
            if (
                (not self.show_mobile and t == "Mobile")
                or (not self.show_early_access and is_early)
                or (self.found_only and not has_d)
            ):
                continue

            if self.search_query and self.search_query.lower() not in searchable_text:
                continue
            if f"{v}||{t}" in seen:
                continue
            seen.add(f"{v}||{t}")
            filtered.append((rss, has_d, stat, el_v, cr_v))

        def sort_key(item):
            v_parts = [int(p) for p in re.findall(r"\d+", item[0].get("version", "0.0.0"))]
            if self.sort_by_priority:
                prio = 0 if item[1] else (1 if item[0].get("type") == "Mobile" else 2)
                return (prio, [-x for x in v_parts])
            return [-x for x in v_parts]

        for idx, (rss, has_d, stat, el_v, cr_v) in enumerate(sorted(filtered, key=sort_key)):

            def hl(val, style=""):
                txt = Text.from_markup(f"[{style}]{val}[/]") if style else Text(str(val))
                if self.search_query:
                    txt.highlight_words([self.search_query], style="bold black on yellow", case_sensitive=False)
                return txt

            def format_ver(v):
                v_str = str(v)
                if any(char.isdigit() for char in v_str):
                    return f"v{v_str}"
                return v_str

            s_style = ""
            if not (self.search_query and self.search_query.lower() in stat.lower()):
                s_style = "b green" if has_d else "b red" if rss.get("type") == "Desktop" else "dim"

            table.add_row(
                str(idx),
                hl(rss.get("version")),
                hl(rss.get("type")),
                hl(rss.get("date")[:10]),
                hl(stat, s_style),
                hl(format_ver(el_v)),
                hl(format_ver(cr_v)),
            )

        self.update_mode_bar()

        self.update_mode_bar()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_submit()

    def action_cursor_down(self):
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self):
        self.query_one(DataTable).action_cursor_up()

    def action_submit(self):
        table = self.query_one(DataTable)
        if table.cursor_row is None:
            return

        row = table.get_row_at(table.cursor_row)
        v_str = row[1].plain if isinstance(row[1], Text) else str(row[1])
        v_str = v_str.strip()

        docker_map = {v["version"]: v for v in self.raw_data.get("docker", [])}
        if v_str not in docker_map:
            self.notify(f"No Docker tag for v{v_str}", severity="error")
            return

        def handle_confirm(choice: bool):
            if choice:
                self.exit(result={"version": v_str, "tag": docker_map[v_str]["tag"]})

        self.push_screen(ConfirmScreen(v_str), handle_confirm)

    def action_toggle_search(self):
        self.query_one("#search-container").add_class("-visible")
        self.query_one("#search-input").focus()
        self.update_mode_bar()

    def action_cancel_search(self):
        self.query_one("#search-container").remove_class("-visible")
        self.search_query = ""
        self.query_one("#search-input").value = ""
        self.update_table()
        self.query_one(DataTable).focus()

    def on_input_changed(self, event: Input.Changed):
        self.search_query = event.value
        self.update_table()

    def on_input_submitted(self):
        self.query_one("#search-container").remove_class("-visible")
        self.query_one(DataTable).focus()

    def action_toggle_mobile(self):
        self.show_mobile = not self.show_mobile
        self.update_table()

    def action_toggle_early(self):
        self.show_early_access = not self.show_early_access
        self.update_table()

    def action_toggle_found(self):
        self.found_only = not self.found_only
        self.update_table()

    def action_toggle_sort(self):
        self.sort_by_priority = not self.sort_by_priority
        self.update_table()

    def update_mode_bar(self):
        bar = self.query_one("#mode-bar")
        is_s = self.query_one("#search-container").has_class("-visible")
        bar.set_classes("mode-search" if is_s else "mode-normal")
        status = f"M:{self.show_mobile} E:{self.show_early_access}"
        bar.update(f"{'[SEARCH]' if is_s else '[NORMAL]'} {status} | Query: '{self.search_query}'")

    def action_next_match(self):
        self.jump_to_match(1)

    def action_prev_match(self):
        self.jump_to_match(-1)

    def jump_to_match(self, d):
        if not self.search_query:
            return
        t = self.query_one(DataTable)
        c, count, q = t.cursor_row, t.row_count, self.search_query.lower()
        for i in range(1, count):
            idx = (c + (i * d)) % count
            if q in " ".join(str(x).lower() for x in t.get_row_at(idx)):
                t.move_cursor(row=idx)
                break


def run_tui(refresh):
    return ObsiVerPicker(force_refresh=refresh).run()
