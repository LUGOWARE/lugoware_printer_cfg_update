"""Shared FLEX4 tool cards for the two KlipperScreen panels."""
from functools import lru_cache
from pathlib import Path

from gi.repository import GdkPixbuf, Gtk, Pango


_ASSET = Path(__file__).with_name("lugo_toolhead.png")
_CSS = b"""
button.lugo-tool-card, button.lugo-tool-card:disabled {
    background: #252525; border: 1px solid #545454; border-radius: .25em;
    padding: .3em; box-shadow: none;
}
button.lugo-tool-card.lugo-tool-mounted, button.lugo-tool-card.lugo-tool-mounted:disabled {
    background: #424242; border-color: #b4b4b4;
}
button.lugo-tool-card:active, button.lugo-tool-card:focus {
    background: #424242; border-color: #b4b4b4;
}
button.lugo-tool-card label, button.lugo-tool-card:disabled label { color: #e2e2e2; }
button.lugo-tool-card label.lugo-tool-status { color: #b8b8b8; font-size: .8em; }
button.lugo-tool-card label.lugo-tool-temp { font-size: .8em; }
button.lugo-tool-neutral, button.lugo-tool-neutral:active, button.lugo-tool-neutral:focus {
    background-image: none; border: 0; border-radius: .25em; box-shadow: none;
}
button.lugo-tool-neutral { background-color: #252525; }
button.lugo-tool-neutral:active, button.lugo-tool-neutral:focus { background-color: #424242; }
.lugo-tool-scrim { background-color: rgba(0, 0, 0, .64); }
.lugo-tool-popup {
    background-color: #121212; border: 1px solid #545454; border-radius: 6px; padding: 11px;
}
"""


def install_style(widget):
    screen = widget.get_screen()
    if screen is not None and screen not in _providers:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        _providers[screen] = provider


_providers = {}


@lru_cache(maxsize=16)
def _picture(height):
    return GdkPixbuf.Pixbuf.new_from_file_at_scale(str(_ASSET), -1, height, True)


def tool_image(height):
    return Gtk.Image.new_from_pixbuf(_picture(height))


def neutral(button):
    button.get_style_context().add_class("lugo-tool-neutral")
    return button


class ToolCard(Gtk.Button):
    def __init__(self, slot, height, show_status=True):
        super().__init__()
        self.get_style_context().add_class("lugo-tool-card")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3,
                          valign=Gtk.Align.CENTER, halign=Gtk.Align.FILL)
        title = Gtk.Label()
        title.set_markup(f"<b>T{slot + 1}</b>")
        self.status = Gtk.Label()
        self.status.get_style_context().add_class("lugo-tool-status")
        self.temperature = Gtk.Label()
        self.temperature.get_style_context().add_class("lugo-tool-temp")
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.temperature.set_line_wrap(True)
        self.temperature.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.temperature.set_max_width_chars(11)
        content.pack_start(title, False, False, 0)
        if show_status:
            content.pack_start(self.status, False, False, 0)
        content.pack_start(tool_image(height), False, False, 0)
        content.pack_start(self.temperature, False, False, 0)
        self.add(content)

    def update(self, status, mounted=False, temperature="—"):
        style = self.get_style_context()
        if mounted:
            style.add_class("lugo-tool-mounted")
        else:
            style.remove_class("lugo-tool-mounted")
        if self.status.get_text() != status:
            self.status.set_text(status)
        if self.temperature.get_text() != temperature:
            self.temperature.set_text(temperature)
