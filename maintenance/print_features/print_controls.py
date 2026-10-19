"""Local .151 trial: touch lock and per-job filament policy controls."""
from gi.repository import Gtk, GLib, Gdk
import re
import threading
import subprocess
import sys
import json
from pathlib import Path


def text(screen, key):
    # Existing catalogs supply standard labels; trial-specific Korean wording.
    lang = screen._config.get_main_config().get('language', 'en')
    ko = {'sensor': '필라멘트 감지', 'waiting': '대기', 'on': 'ON', 'off': 'OFF',
          'lock': '화면 잠금', 'unlock': '1초 눌러 잠금 해제',
          'estop': '비상정지', 'confirm': '비상정지를 실행할까요?',
          'cancel': '취소'}
    en = {'sensor': 'Filament sensor', 'waiting': 'Waiting', 'on': 'ON', 'off': 'OFF',
          'lock': 'Lock screen', 'unlock': 'Hold 1s to unlock',
          'estop': 'Emergency Stop', 'confirm': 'Run Emergency Stop?', 'cancel': 'Cancel'}
    return (ko if lang.startswith('ko') else en)[key]


def set_policy(screen, enabled, callback=None, finished=None, scope=None):
    def done(result, *args):
        if finished:
            finished(result)
        if 'error' in result:
            screen.show_popup_message(str(result['error'].get('message', result['error'])))
        elif callback:
            callback()
    if not screen._ws.send_method('printer.print_sensor.policy',
            {'enabled': int(enabled), 'scope': scope or ('next' if callback else 'current')}, done):
        if finished:
            finished()
        screen.show_popup_message('Printer connection unavailable')


def sensor_row(screen, active=True):
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5,
                  valign=Gtk.Align.CENTER, hexpand=True)
    row.get_style_context().add_class('trial-sensor-pill')
    label = screen.gtk.Button('spool', text(screen, 'sensor'), None,
                              screen.gtk.bsidescale, Gtk.PositionType.LEFT, 1)
    label.set_halign(Gtk.Align.START)
    size = int(screen.gtk.img_scale * screen.gtk.bsidescale)
    label.get_image().set_size_request(size, size)
    label.get_image().set_halign(Gtk.Align.CENTER)
    label.get_style_context().add_class('trial-sensor-caption')
    switch = Gtk.Switch(active=active, valign=Gtk.Align.CENTER, halign=Gtk.Align.END)
    row.pack_start(label, True, True, 0)
    row.pack_end(switch, False, False, 0)
    row.set_margin_start(1)
    row.set_margin_end(6)
    return row, switch, label


def install_style():
    provider = Gtk.CssProvider()
    provider.load_from_data(b'''
        .trial-sensor-pill { border: none; border-radius: 0;
            background-color: transparent; padding: 0; }
        .trial-sensor-caption { background-color: transparent; }
        .trial-sensor-pill switch { min-width: 58px; min-height: 28px; margin: 0; }
        .trial-sensor-pill switch slider { min-width: 26px; min-height: 26px; }
        .trial-sensor-pill switch, .trial-sensor-pill switch slider { transition: none; }
        .trial-sensor-pill switch:disabled,
        .trial-sensor-pill switch:disabled:checked {
            opacity: 0.4; background-image: none; background-color: #444444;
            border-color: #555555; }
        .trial-sensor-pill switch:disabled slider {
            background-image: none; background-color: #999999; }
        .trial-lock { padding: 4px; margin: 5px; border-radius: 10px;
            background-color: #252525; border: 1px solid #454545; }
        .trial-lock label { font-size: 14px; }
    ''')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, 810)
    return provider


class TouchLock:
    def __init__(self, screen):
        self.screen = screen
        self.timer = None
        self.layer = None
        self.saved = []
        self.button = None
        self.caption = None
        self.fill_provider = None
        self.fill_fraction = 0.0
        self.hold_start = None

    def open(self, *args):
        if self.layer is not None:
            return
        self.layer = True
        allowed = (self.button, self.screen.base_panel.control['estop'])
        def visit(widget):
            if widget in allowed:
                return
            if any(a.is_ancestor(widget) for a in allowed):
                if isinstance(widget, Gtk.Container):
                    for child in widget.get_children():
                        visit(child)
            else:
                self.saved.append((widget, widget.get_sensitive()))
                widget.set_sensitive(False)
        visit(self.screen.base_panel.main_grid)
        self.caption.set_text('해제' if text(self.screen,'lock')=='화면 잠금' else 'Unlock')

    def press(self, *args):
        if self.layer is None:
            self.open()
            return
        self.release()
        self.hold_start = GLib.get_monotonic_time()
        self.timer = GLib.timeout_add(16, self.advance)

    def advance(self):
        fraction = min(1.0, (GLib.get_monotonic_time() - self.hold_start) / 1000000.0)
        self.set_fill(fraction)
        if fraction >= 1.0:
            return self.unlock()
        return True

    def release(self, *args):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        self.hold_start = None
        self.set_fill(0)
        return False

    def set_fill(self, fraction):
        self.fill_fraction = fraction
        if self.fill_provider is None:
            return
        percent = fraction * 100
        if fraction <= 0:
            image = 'none'
        else:
            image = ('linear-gradient(to top, alpha(@theme_selected_bg_color, 0.65) 0%, '
                     f'alpha(@theme_selected_bg_color, 0.65) {percent:.2f}%, '
                     f'transparent {percent:.2f}%, transparent 100%)')
        self.fill_provider.load_from_data(
            ('.trial-lock { background-image: ' + image + '; }').encode())

    def unlock(self):
        self.timer = None
        self.close()
        return False

    def close(self):
        self.release()
        if self.layer is not None:
            self.layer = None
        for widget, sensitive in self.saved:
            widget.set_sensitive(sensitive)
        self.saved = []
        if self.button:
            self.caption.set_text('잠금' if text(self.screen,'lock')=='화면 잠금' else 'Lock')

    def estop(self, widget):
        self.release()
        # Always confirm, independent of the normal confirm_estop preference.
        self.screen._confirm_send_action(widget, text(self.screen, 'confirm'), 'printer.emergency_stop')


def add_controls(panel, info):
    screen = panel._screen
    if not hasattr(screen, 'trial_touch_lock'):
        screen.trial_touch_lock = TouchLock(screen)
    screen._trial_style = install_style()
    lock = Gtk.Button(halign=Gtk.Align.END, valign=Gtk.Align.START)
    lock_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       valign=Gtk.Align.CENTER)
    lock_box.pack_start(screen.gtk.Image('lock', 28, 28), False, False, 0)
    caption = Gtk.Label(label='잠금' if text(screen,'lock')=='화면 잠금' else 'Lock')
    lock_box.pack_start(caption, False, False, 0)
    lock.add(lock_box)
    lock.set_size_request(112, 84)
    lock.set_no_show_all(True)
    screen.trial_touch_lock.caption = caption
    screen.trial_touch_lock.fill_provider = Gtk.CssProvider()
    lock.get_style_context().add_provider(screen.trial_touch_lock.fill_provider, 820)
    lock.get_style_context().add_class('trial-lock')
    lock.connect('pressed', screen.trial_touch_lock.press)
    lock.connect('released', screen.trial_touch_lock.release)
    lock.connect('leave-notify-event', screen.trial_touch_lock.release)
    lock.connect('grab-broken-event', screen.trial_touch_lock.release)
    screen.trial_touch_lock.button = lock
    sensor, switch, label = sensor_row(screen)
    panel._sensor_sync = False
    panel._sensor_pending = False
    def toggle(widget, _property):
        if panel._sensor_sync:
            return
        if panel._sensor_pending:
            return
        panel._sensor_pending = True
        widget.set_sensitive(False)
        def finished(result=None):
            panel._sensor_pending = False
            if result and 'result' in result:
                panel._printer.data.setdefault('print_sensor', {}).update(result['result'])
            update_controls(panel)
        scope = 'current' if panel.state in ('printing', 'paused') else 'next'
        set_policy(screen, widget.get_active(), finished=finished, scope=scope)
    switch.connect('notify::active', toggle)
    panel.buttons['trial_lock'] = lock
    panel.buttons['trial_sensor'] = sensor
    panel._sensor_switch = switch
    panel._sensor_label = label
    toolchange = screen.gtk.Button('toolchanger-requested', '툴체인지 0/…' if
        screen._config.get_main_config().get('language', 'en').startswith('ko')
        else 'Tool changes 0', None, screen.gtk.bsidescale, Gtk.PositionType.LEFT, 1)
    toolchange.set_halign(Gtk.Align.START)
    toolchange.set_valign(Gtk.Align.CENTER)
    size = int(screen.gtk.img_scale * screen.gtk.bsidescale)
    toolchange.get_image().set_size_request(size, size)
    toolchange.get_image().set_halign(Gtk.Align.CENTER)
    toolchange.get_image().set_margin_end(2)
    from ks_includes.KlippyGtk import find_widget
    toolchange_text = find_widget(toolchange, Gtk.Label)
    if toolchange_text is not None:
        toolchange_text.set_margin_start(0)
    toolchange_box = find_widget(toolchange, Gtk.Box)
    if toolchange_box is not None:
        toolchange_box.set_spacing(4)
    toolchange.get_style_context().add_class('trial-sensor-caption')
    toolchange.set_margin_start(1)
    panel._toolchange_label = toolchange
    panel._toolchange_count = '0'
    panel._toolchange_file = None
    panel._toolchange_total = None
    info.attach(toolchange, 1, 3, 1, 1)
    info.attach(sensor, 1, 4, 1, 1)


def mount_controls(panel):
    overlay = Gtk.Overlay(hexpand=True, vexpand=True)
    overlay.add(panel.grid)
    lock = panel.buttons['trial_lock']
    overlay.add_overlay(lock)

    def position(container, child, allocation):
        if child is not lock:
            return False
        thumb = panel.labels['thumbnail']
        coords = thumb.translate_coordinates(panel.grid, 0, 0)
        if coords is None:
            return False
        width = child.get_preferred_width()[1]
        height = child.get_preferred_height()[1]
        allocation.x = max(0, container.get_allocated_width() - width)
        allocation.y = max(0, coords[1] - 30)
        allocation.width = width
        allocation.height = height
        return True

    overlay.connect('get-child-position', position)
    panel.content.add(overlay)


def update_controls(panel):
    filename = panel._printer.get_stat('print_stats', 'filename')
    if filename != panel._toolchange_file:
        panel._toolchange_file = filename
        panel._toolchange_count = '0'
        panel._toolchange_total = None
        if filename and not (panel._printer.get_stat('gcode_macro TOOL_STATE') or {}).get('tc_total', 0):
            root = panel._printer.get_config_section('virtual_sdcard').get('path', '')
            def scan():
                total = None
                try:
                    result = subprocess.run(
                        [sys.executable, str(Path(__file__).with_name('toolchange_count.py')), root, filename],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        text=True, timeout=120, check=True)
                    total = json.loads(result.stdout)['total']
                    if type(total) is not int or total < 0:
                        total = None
                except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                    pass
                def ready():
                    if panel._toolchange_file == filename:
                        panel._toolchange_total = total
                        update_controls(panel)
                    return False
                GLib.idle_add(ready)
            def start_scan():
                if panel._toolchange_file == filename and panel.content.get_mapped():
                    threading.Thread(target=scan, daemon=True).start()
                return False
            def defer_scan():
                # Paint the print panel first. CPU-heavy parsing runs in another process.
                GLib.timeout_add(350, start_scan, priority=GLib.PRIORITY_DEFAULT_IDLE)
            if panel.content.get_mapped():
                defer_scan()
            else:
                def mapped(widget):
                    widget.disconnect(handler)
                    defer_scan()
                handler = panel.content.connect('map', mapped)
    message = str(panel._printer.get_stat('display_status', 'message') or '')
    match = re.search(r'\bTC\s+(\d+(?:/\d+)?)', message)
    if match:
        panel._toolchange_count = match.group(1)
    tc = panel._printer.get_stat('gcode_macro TOOL_STATE') or {}
    current = tc.get('tc_count', int(panel._toolchange_count.split('/')[0]))
    total = tc.get('tc_total', 0) or panel._toolchange_total
    if not total and '/' in panel._toolchange_count:
        total = int(panel._toolchange_count.split('/')[1])
    name = '툴체인지' if panel._screen._config.get_main_config().get('language', 'en').startswith('ko') else 'Tool changes'
    label = f'{name} {current}/{total if total is not None else "…"}'
    if panel._toolchange_label.get_label() != label:
        panel._toolchange_label.set_label(label)
    controller = panel._screen.trial_touch_lock
    in_print = panel.state in ('printing', 'paused')
    if not in_print:
        controller.close()
    panel.buttons['trial_lock'].set_visible(in_print)
    if in_print:
        panel.buttons['trial_lock'].get_child().show_all()
    data = panel._printer.get_stat('print_sensor') or {}
    state = data.get('state', 'waiting')
    sensor = panel.buttons.get('trial_sensor')
    if sensor:
        if not panel._sensor_pending:
            panel._sensor_sync = True
            enabled = bool(data.get('enabled', True))
            if panel._sensor_switch.get_active() != enabled:
                panel._sensor_switch.set_active(enabled)
            if panel._sensor_switch.get_state() != enabled:
                panel._sensor_switch.set_state(enabled)
            panel._sensor_sync = False
        panel._sensor_switch.set_sensitive(not panel._sensor_pending)
        unlocked = panel._screen.trial_touch_lock.layer is None
        sensor.set_sensitive(unlocked)
