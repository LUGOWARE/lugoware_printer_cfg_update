"""Pre-print status dialog; GTK updates only on the screen main loop."""
from gi.repository import Gtk, GLib
import time
import logging

def update(screen, data):
    value = data.get('lugo_preanalysis')
    if value is None: return
    if not hasattr(screen, '_preanalysis_ui'):
        screen._preanalysis_ui = Notice(screen)
    screen._preanalysis_ui.update(value)

class Notice:
    def __init__(self, screen):
        self.screen=screen; self.dialog=None; self.state={}; self.timer=None; self.dots=0
        self.shown=0.; self.target=0.; self.origin=0.; self.changed=0.; self.dot_time=0.
        self.full_at=None; self.ack_sent=False; self.generation=None

    def update(self, value):
        self.state.update(value)
        if self.state.get('state') in ('reading', 'finishing'):
            generation=self.state.get('generation')
            if generation != self.generation:
                self.close(); self.generation=generation
            if self.dialog is None: self.open()
            target=1. if self.state.get('state') == 'finishing' else max(0.,min(1.,self.state.get('progress',0.)))
            if target > self.target:
                self.origin=self.shown; self.target=target; self.changed=time.monotonic()
        elif self.dialog is not None:
            self.close()
            if self.state.get('state') == 'error':
                self.screen.show_popup_message('G-code: ' + self.state.get('error',''), 3)

    def close(self):
        if self.dialog is not None: self.dialog.destroy(); self.dialog=None
        if self.timer: GLib.source_remove(self.timer); self.timer=None

    def open(self):
        self.dialog=Gtk.Dialog(transient_for=self.screen, modal=True)
        width, height = self.screen.get_size()
        self.dialog.set_decorated(False)
        self.dialog.set_default_size(width, height)
        self.dialog.set_size_request(width, height)
        self.dialog.fullscreen()
        self.dialog.set_title('G-code')
        self.dialog.set_name('lugo-analysis-dialog')
        self.css=Gtk.CssProvider()
        self.css.load_from_data(b"""
            #lugo-analysis-dialog, #lugo-analysis-dialog decoration { background-color: #121212; color: #e2e2e2; }
            #lugo-analysis-dialog box, #lugo-analysis-dialog label { background-color: transparent; color: #e2e2e2; }
            #lugo-analysis-dialog button { background-image: none; background-color: #242424; color: #e2e2e2; border: 0; border-radius: 4px; padding: 12px; }
            #lugo-analysis-dialog progressbar trough { background-color: #242424; border: 0; min-height: 24px; border-radius: 4px; }
            #lugo-analysis-dialog progressbar progress { background-image: none; background-color: #305b32; border: 0; min-height: 24px; border-radius: 4px; }
        """)
        self.shown=self.target=self.origin=0.
        self.full_at=None; self.ack_sent=False
        self.changed=self.dot_time=time.monotonic()
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_margin_start(24);box.set_margin_end(24)
        box.set_margin_top(35);box.set_margin_bottom(35)
        box.set_valign(Gtk.Align.CENTER);box.set_vexpand(True)
        lang=self.screen._config.get_main_config().get('language','en')
        self.text = 'G-code 읽는 중' if lang.startswith('ko') else ('正在读取 G-code' if lang.startswith('zh') else 'Reading G-code')
        title=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        title.set_halign(Gtk.Align.CENTER)
        self.label=Gtk.Label(label=self.text)
        self.dot_label=Gtk.Label(label='.')
        self.dot_label.set_width_chars(3);self.dot_label.set_max_width_chars(3)
        self.dot_label.set_xalign(0.)
        title.pack_start(self.label,False,False,0);title.pack_start(self.dot_label,False,False,0)
        box.pack_start(title,False,False,0)
        self.thumbnail=Gtk.Image.new_from_icon_name('text-x-generic', Gtk.IconSize.DIALOG)
        self.thumbnail.set_size_request(-1, max(120, int(height * .38)))
        box.pack_start(self.thumbnail,False,False,0)
        self.load_thumbnail(max(100, width-64), max(120, int(height*.38)))
        self.bar=Gtk.ProgressBar();self.bar.set_show_text(True);self.bar.set_size_request(-1,36)
        box.pack_start(self.bar,False,False,0)
        button=Gtk.Button(label='취소' if lang.startswith('ko') else ('取消' if lang.startswith('zh') else 'Cancel'))
        button.connect('clicked',self.cancel);box.pack_start(button,False,False,0)
        self.dialog.get_content_area().add(box)
        self.dialog.connect('delete-event',lambda *args: True)
        def style(widget):
            widget.get_style_context().add_provider(self.css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+100)
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():style(child)
        style(self.dialog)
        self.bar.set_fraction(0.);self.bar.set_text('0%')
        self.dialog.show_all();self.timer=GLib.timeout_add(33,self.animate)

    def load_thumbnail(self, width, height):
        # Use existing metadata and image workers; never scan the G-code here.
        dialog=self.dialog; generation=self.generation; image=self.thumbnail
        def apply(pixbuf):
            if self.dialog is dialog and self.generation == generation and pixbuf is not None:
                image.set_from_pixbuf(pixbuf)
            return False
        try:
            filename=self.state.get('filename','')
            files=self.screen.files
            actual=self.screen.printer.get_stat('print_stats','filename')
            if actual and actual.rsplit('/',1)[-1] == filename:
                filename=actual
            if not files.has_thumbnail(filename): return
            loc=files.get_thumbnail_location(filename)
            if not loc: return
            gtk=self.screen.gtk
            if loc[0] == 'file':
                def load():
                    try: pixbuf=gtk.PixbufFromFile(loc[1],width,height)
                    except Exception:
                        logging.exception('Preanalysis thumbnail unavailable')
                        return
                    GLib.idle_add(apply,pixbuf)
                gtk._executor.submit(load)
            else:
                gtk.PixbufFromHttpAsync(loc[1],width,height,apply)
        except Exception:
            logging.exception('Preanalysis thumbnail unavailable')

    def cancel(self,*args):
        self.screen._ws.send_method('printer.gcode.script',{'script':'LUGO_ANALYSIS_CANCEL'})

    def animate(self):
        if self.dialog is None: return False
        now=time.monotonic()
        if now-self.dot_time >= .45:
            self.dots=self.dots%3+1;self.dot_label.set_text('.'*self.dots);self.dot_time=now
        t=min(1.,max(0.,(now-self.changed)/.75))
        fraction=self.origin+(self.target-self.origin)*(1.-(1.-t)**3)
        if t >= 1.: fraction=self.target
        if fraction != self.shown:
            self.shown=fraction;self.bar.set_fraction(fraction)
            self.bar.set_text('%d%%' % round(fraction*100))
        if self.state.get('state') == 'finishing' and self.shown == 1.:
            if self.full_at is None: self.full_at=now
            if now-self.full_at >= .25 and not self.ack_sent:
                self.ack_sent=True
                self.screen._ws.send_method('printer.gcode.script',
                    {'script':'LUGO_ANALYSIS_CONTINUE GENERATION=%d' % self.generation})
        return True
