import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    _lugo_provider = None

    def __init__(self, screen, title):
        title = title or _("Settings")
        super().__init__(screen, title)
        self.printers = self.settings = self.langs = {}
        self.menu = ["settings_menu"]
        options = self._config.get_configurable_options().copy()
        options.append(
            {"printers": {"name": _("Printer Connections"), "type": "menu", "menu": "printers"}}
        )
        options.append({"lang": {"name": _("Language"), "type": "menu", "menu": "lang"}})
        options = [item for item in options if "printers" not in item]
        self.labels["settings_menu"] = self._gtk.ScrolledWindow()
        self.labels["settings"] = Gtk.Grid()
        self.labels["settings_menu"].add(self.labels["settings"])
        for option in options:
            name = list(option)[0]
            self.add_option("settings", self.settings, name, option[name])

        self.labels["lang_menu"] = self._gtk.ScrolledWindow()
        self.labels["lang"] = Gtk.Grid()
        self.labels["lang_menu"].add(self.labels["lang"])
        from ks_includes.lugo_language_names import language_name
        for lang in self._config.lang_list:
            self.langs[lang] = {
                "name": language_name(lang),
                "type": "button",
                "callback": lambda widget, name, code=lang: self._screen.change_language(widget, code),
            }
            self.add_option("lang", self.langs, lang, self.langs[lang])

        self.labels["printers_menu"] = self._gtk.ScrolledWindow()
        self.labels["printers"] = Gtk.Grid()
        self.labels["printers_menu"].add(self.labels["printers"])
        for printer in self._config.get_printers():
            pname = list(printer)[0]
            self.printers[pname] = {
                "name": pname,
                "section": f"printer {pname}",
                "type": "printer",
                "moonraker_host": printer[pname]["moonraker_host"],
                "moonraker_port": printer[pname]["moonraker_port"],
            }
            self.add_option("printers", self.printers, pname, self.printers[pname])

        # LUGOWARE timezone settings (system setting survives config updates).
        from panels.timezone import setting_title
        zone_title = setting_title(self._config.get_main_config())
        self.add_option('settings', self.settings, 'timezone', {
            'name': zone_title, 'type': 'button',
            'callback': lambda widget, name: self._screen.show_panel('timezone', title=zone_title),
        })
        self.content.get_style_context().add_class("lugo-settings")
        for key in ("settings", "lang", "printers"):
            grid = self.labels[key]
            grid.set_row_spacing(8)
            grid.set_margin_start(8)
            grid.set_margin_end(8)
            grid.set_margin_top(6)
            grid.set_margin_bottom(8)
        if Panel._lugo_provider is None:
            provider = Gtk.CssProvider()
            provider.load_from_data(b'\n                .lugo-settings .frame-item {\n                    background-color: #252525; \n                     padding: 12px; margin: 0;\n                 border: 0; border-radius: .25em; }\n                .lugo-settings button {\n                    background-image: none; background-color: #252525;\n                     \n                    box-shadow: none; text-shadow: none;\n                  border-radius: .25em;  border: 1px solid #505050; }\n                .lugo-settings button:active, .lugo-settings button:checked {\n                    background-color: #087da5; \n                  border-radius: .25em;  border-color: #66dcff; }\n                .lugo-settings button:disabled { background-color: #282828;   border-radius: .25em;   }\n                .lugo-settings switch {\n                    background-image: none; background-color: #111111;\n                    border: 1px solid #484848; border-radius: 20px;\n                }\n                .lugo-settings switch:checked { background-color: #305730; }\n                .lugo-settings switch slider {\n                    background-image: none; background-color: #eeeeee;\n                    border: 1px solid #bbbbbb; border-radius: 20px;\n                }\n                .lugo-settings scale trough {\n                    background-color: #111111; border: 1px solid #484848;\n                    border-radius: 6px; min-height: 10px;\n                }\n                .lugo-settings scale highlight { background-color: #305730; border-radius: 6px; }\n                .lugo-settings scale slider {\n                    background-image: none; background-color: #eeeeee;\n                    border: 1px solid #bbbbbb; border-radius: 20px;\n                }\n            \n.lugo-settings button, .lugo-settings button:active, .lugo-settings button:disabled,\n.lugo-settings button.button_active, .lugo-settings button.lugo-diameter,\n.lugo-settings button.lugo-selected, .lugo-settings button.lugo-diameter.lugo-selected { border: 0; }\n.lugo-settings .frame-item button, .lugo-settings .tz-current button { border: 1px solid #505050; }\n')
            Gtk.StyleContext.add_provider_for_screen(self.content.get_screen(), provider,
                                                     Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            Panel._lugo_provider = provider
        self.content.add(self.labels["settings_menu"])
