"""Local timezone selection using the OS timezone database; no config reset."""
from datetime import datetime
import gettext
import json
import locale
from pathlib import Path
import subprocess
import threading
import time
from zoneinfo import ZoneInfo

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk, Pango
from ks_includes.screen_panel import ScreenPanel

def translations(config):
    language = config.get('language', 'en')
    if language == 'system_lang': language = locale.getlocale()[0] or 'en'
    language = {'ja':'jp', 'sr':'rs'}.get(language, language)
    folder = Path(__file__).with_name('timezone_locales')
    for key in (language, language.split('_')[0], 'en'):
        if not key.replace('_','').isalpha(): continue
        path = folder / (key + '.json')
        if path.is_file(): return json.loads(path.read_text(encoding='utf-8')), key
    raise RuntimeError('Timezone translations are missing')


def setting_title(config):
    return translations(config)[0]['ui']['Time zone']


def zones():
    result = {}
    for line in Path('/usr/share/zoneinfo/zone.tab').read_text().splitlines():
        if not line or line.startswith('#'): continue
        country, coordinates, zone, *comment = line.split('\t')
        for code in country.split(','):
            result.setdefault(code, []).append(zone)
    return result


def current_zone():
    try:
        return str(Path('/etc/localtime').resolve()).split('/zoneinfo/', 1)[1]
    except (OSError, IndexError):
        return Path('/etc/timezone').read_text().strip()


class Panel(ScreenPanel):
    _lugo_provider = None
    _style = None
    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.content.get_style_context().add_class("lugo-theme")
        if Panel._lugo_provider is None:
            provider = Gtk.CssProvider()
            provider.load_from_data(b'\n            .lugo-theme button {\n                background-image: none; background-color: #252525;\n                 \n                box-shadow: none; text-shadow: none;\n              border-radius: .25em;  border: 1px solid #505050; }\n            .lugo-theme button:active, .lugo-theme button:checked,\n            .lugo-theme button.button_active {\n                background-color: #087da5; \n              border-radius: .25em;  border-color: #66dcff; }\n            .lugo-theme button:disabled { background-color: #282828;    border-radius: .25em;  border-color: #383838; }\n            .lugo-theme .frame-item, .lugo-theme .tz-current {\n                background-color: #252525; \n                \n             border: 0; border-radius: .25em; }\n            .lugo-theme .timezone-panel button.tz-apply {     border-radius: .25em;  border: 1px solid #505050; }\n            .lugo-theme entry {\n                background-image: none; background-color: #181818;\n                border: 1px solid #505050; border-radius: 7px; color: #eeeeee;\n            }\n            .lugo-theme entry:focus { border-color: #66dcff; }\n            .lugo-theme textview, .lugo-theme textview text { background-color: #181818; }\n            .lugo-theme switch { background-image: none; background-color: #111111; border: 1px solid #484848; border-radius: 20px; }\n            .lugo-theme switch:checked { background-color: #305730; }\n            .lugo-theme switch slider { background-image: none; background-color: #eeeeee; border-radius: 20px; }\n\n.lugo-theme button, .lugo-theme button:active, .lugo-theme button:disabled,\n.lugo-theme button.button_active, .lugo-theme button.lugo-diameter,\n.lugo-theme button.lugo-selected, .lugo-theme button.lugo-diameter.lugo-selected { border: 0; }\n.lugo-theme .frame-item button, .lugo-theme .tz-current button { border: 1px solid #505050; }\n')
            Gtk.StyleContext.add_provider_for_screen(self.content.get_screen(), provider,
                                                     Gtk.STYLE_PROVIDER_PRIORITY_USER + 3)
            Panel._lugo_provider = provider

        self.catalog, self.language = translations(self._config.get_main_config())
        self.tr = lambda text: self.catalog['ui'].get(text, text)
        self.countries = zones()
        self.names = self.catalog['countries']
        self.selected = current_zone()
        self.country = next((c for c,z in self.countries.items() if self.selected in z), 'KR')
        self.page = 'main'
        self.busy = False
        self.active = False
        self.timer = None
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True, vexpand=True)
        self.box.set_border_width(8)
        self.box.get_style_context().add_class('timezone-panel')
        if self.language in ('ar','fa','he'):
            self.box.set_direction(Gtk.TextDirection.RTL)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .timezone-panel label { font-size: 19px; }
            .timezone-panel .tz-caption { font-size: 17px; }
            .timezone-panel .tz-value { font-size: 25px; font-weight: bold; }
            .timezone-panel .tz-current { border-radius: 10px; padding: 12px; }
            .timezone-panel button { background-image: none; box-shadow: none; text-shadow: none; border-width: 2px; border-style: solid;
                border-radius: 10px; padding: 10px; }
            .timezone-panel button.tz-apply { border-width: 3px; }
        """)
        # Scoped selectors do not affect other panels.
        if Panel._style is None:
            Panel._style = css
            Gtk.StyleContext.add_provider_for_screen(self.content.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        self.content.add(self.box)
        self.draw_main()

    def label(self, text, style=None):
        label = Gtk.Label(label=text, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                          justify=Gtk.Justification.CENTER, max_width_chars=26)
        if style: label.get_style_context().add_class(style)
        return label

    def button(self, text, callback, *args):
        button = Gtk.Button(hexpand=True)
        button.get_style_context().add_class('color1')
        button.add(self.label(text))
        button.set_size_request(-1, 62)
        button.connect('clicked', callback, *args)
        return button

    def selection(self, caption, value, callback):
        button = Gtk.Button(hexpand=True)
        button.get_style_context().add_class('color1')
        row = Gtk.Box(spacing=8)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True)
        labels.pack_start(self.label(caption, 'tz-caption'), False, False, 0)
        labels.pack_start(self.label(value, 'tz-value'), False, False, 0)
        row.pack_start(labels, True, True, 0)
        row.pack_end(self.label('‹' if self.language in ('ar','fa','he') else '›', 'tz-value'), False, False, 4)
        button.add(row)
        button.set_size_request(-1, 96)
        button.connect('clicked', callback)
        return button

    def clear(self):
        for child in self.box.get_children(): child.destroy()

    def city(self, zone):
        return self.catalog['cities'].get(zone, zone.rsplit('/',1)[-1].replace('_',' '))

    def draw_main(self):
        self.page = 'main'
        self.clear()
        self.current = self.label('', 'tz-caption')
        self.current.get_style_context().add_class('tz-current')
        self.box.pack_start(self.current, False, False, 0)
        self.country_button = self.selection(self.tr('Country'), self.names.get(self.country,self.country), self.show_countries)
        self.box.pack_start(self.country_button, False, False, 0)
        self.city_button = self.selection(self.tr('City / time zone'), self.city(self.selected), self.show_cities)
        self.box.pack_start(self.city_button, False, False, 0)
        self.preview = self.label('')
        self.box.pack_start(self.preview, True, True, 8)
        self.result = self.label('', 'tz-caption')
        self.box.pack_start(self.result, False, False, 0)
        self.apply_button = self.button(self.tr('Apply'), self.apply)
        self.apply_button.get_style_context().remove_class('color1')
        self.apply_button.get_style_context().add_class('color3')
        self.apply_button.get_style_context().add_class('tz-apply')
        self.box.pack_start(self.apply_button, False, False, 0)
        self.refresh()
        self.box.show_all()

    def refresh(self):
        if self.page == 'main':
            time.tzset()
            self.current.set_text(self.tr('Current') + ': ' + self.city(current_zone()) + '\n' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            local = datetime.now(ZoneInfo(self.selected))
            offset = local.strftime('%z')
            self.preview.set_text(self.tr('Preview') + '\n' + local.strftime('%Y-%m-%d %H:%M:%S') + '\n' + self.selected + '\nUTC' + offset[:3] + ':' + offset[3:])
        return True

    def show_list(self, title, choices, callback):
        if self.busy: return
        self.clear()
        self.box.pack_start(self.label(title), False, False, 0)
        scroll = self._gtk.ScrolledWindow()
        listing = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for key, label in choices:
            listing.pack_start(self.button(label, callback, key), False, False, 0)
        scroll.add(listing)
        self.box.pack_start(scroll, True, True, 0)
        self.box.show_all()

    def show_countries(self, widget=None):
        if self.busy: return
        self.page = 'countries'
        keys = sorted(self.countries, key=lambda c:self.names.get(c,c))
        keys.remove(self.country); keys.insert(0,self.country)
        self.show_list(self.tr('Country'), [(c,self.names.get(c,c)) for c in keys], self.choose_country)

    def choose_country(self, widget, country):
        self.country = country
        if self.selected not in self.countries[country]: self.selected = self.countries[country][0]
        self.show_cities()

    def show_cities(self, widget=None):
        if self.busy: return
        self.page = 'cities'
        self.show_list(self.names.get(self.country,self.country), [(z,self.city(z)+'\n'+z) for z in self.countries[self.country]], self.choose_city)

    def choose_city(self, widget, zone):
        self.selected = zone
        self.draw_main()

    def apply(self, widget):
        if self.busy or self.selected not in self.countries[self.country]: return
        self.busy = True
        for button in (self.apply_button,self.country_button,self.city_button): button.set_sensitive(False)
        self.result.set_text(self.tr('Applying…'))
        zone = self.selected
        def run():
            try:
                subprocess.run(['/usr/bin/timedatectl','--no-ask-password','set-timezone',zone], check=True, capture_output=True, timeout=20)
                ok = current_zone() == zone
            except (OSError, subprocess.SubprocessError): ok = False
            GLib.idle_add(self.applied, ok)
        threading.Thread(target=run,daemon=True).start()

    def applied(self, ok):
        self.busy = False
        time.tzset()
        if self.active and self.page == 'main':
            for button in (self.apply_button,self.country_button,self.city_button): button.set_sensitive(True)
            self.result.set_text(self.tr('Applied') if ok else self.tr('Unable to change timezone. Administrator setup is required.'))
            self.refresh()
        return False

    def back(self):
        if self.busy: return True
        if self.page != 'main':
            self.draw_main()
            return True
        return False

    def activate(self):
        self.active = True
        self.selected = current_zone()
        self.country = next((c for c,z in self.countries.items() if self.selected in z),self.country)
        self.draw_main()
        if self.timer is None: self.timer = GLib.timeout_add_seconds(1,self.refresh)

    def deactivate(self):
        self.active = False
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
