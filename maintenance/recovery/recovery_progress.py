"""Recovery preparation screen. Does not initiate printer operations on entry."""
from gi.repository import Gtk, GLib
from ks_includes.screen_panel import ScreenPanel
from panels.recovery import tr
from ks_includes.recovery_files import style_dialog


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or tr(screen, 'Print recovery'))
        self.timer = None
        self.pending = False
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_border_width(16)
        self.name = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.thumbnail_size = int(min(screen.width * .65, screen.height * .38))
        self.thumbnail = self._gtk.Image('file', self.thumbnail_size, self.thumbnail_size)
        self.thumbnail.set_halign(Gtk.Align.CENTER)
        self.thumbnail.set_valign(Gtk.Align.CENTER)
        self.thumbnail_file = None
        self.stage = Gtk.Label(label=tr(screen, 'Recovery setup is running.'), wrap=True,
                               justify=Gtk.Justification.CENTER, vexpand=True)
        self.temps = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.stop = Gtk.Button(label=tr(screen, 'Stop recovery'))
        self.stop.connect('clicked', self.abort)
        for widget in (self.name, self.thumbnail, self.stage, self.temps, self.stop):
            box.pack_start(widget, widget is self.stage, True, 0)
        self.content.add(box)
        style_dialog(box)

    def activate(self):
        if self.timer is None:
            self.timer = GLib.timeout_add_seconds(1, self.poll)
        self.poll()

    def deactivate(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def poll(self):
        if not self.pending:
            self.pending = True
            if not self._screen._ws.send_method('printer.lugo_recovery.control',
                    {'action': 'status'}, self.received):
                self.pending = False
                self.stage.set_text(tr(self._screen, 'Check printer connection.'))
        return True

    def received(self, response, *args):
        self.pending = False
        if self.timer is None: return
        if 'error' in response:
            self.stage.set_text(tr(self._screen, response['error'].get('message', str(response['error']))))
            return
        data = response.get('result', {})
        state = data.get('state', {})
        self.name.set_text(data.get('record', {}).get('filename', ''))
        filename = data.get('record', {}).get('filename', '')
        if filename and filename != self.thumbnail_file:
            self.thumbnail_file = filename
            def loaded(pixbuf):
                if self.thumbnail_file == filename and pixbuf is not None:
                    self.thumbnail.set_from_pixbuf(pixbuf)
            self.load_image_async(filename, self.thumbnail_size, self.thumbnail_size, callback=loaded)
        messages = {'homing': 'Homing XY…', 'heating': 'Heating…',
                    'docking': 'Docking and priming…', 'returning': 'Returning to the print…'}
        self.stage.set_text(tr(self._screen, state.get('error') or
            messages.get(state.get('stage'), 'Recovery setup is running.')))
        self.stop.set_sensitive(bool(state.get('recovering')))
        parts = []
        for heater, label in (('extruder', 'Nozzle'), ('heater_bed', 'Bed')):
            current = self._printer.get_stat(heater, 'temperature') or 0
            target = self._printer.get_stat(heater, 'target') or 0
            parts.append(f'{tr(self._screen, label)}: {current:.0f} / {target:.0f} °C')
        self.temps.set_text('\n'.join(parts))
        # Normal print_stats transition selects job_status; never fake printing
        # while setup is still moving or heating.

    def abort(self, button):
        button.set_sensitive(False)
        self._screen._ws.send_method('printer.lugo_recovery.control', {'action': 'abort'})
