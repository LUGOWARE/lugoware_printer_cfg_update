"""File-scoped recovery choice. No startup popup and no implicit print start."""
from pathlib import PurePosixPath
from gi.repository import Gtk, GLib
from panels.recovery import tr


def normalized(name):
    name = str(name or '')
    if name.startswith('gcodes/'): name = name[7:]
    return str(PurePosixPath(name))


def matches(result, filename):
    return bool(result.get('state', {}).get('available') and
                result.get('record', {}).get('session') and
                normalized(result['record'].get('filename')) == normalized(filename))


def style_dialog(dialog):
    dialog.get_style_context().add_class('recovery-file-dialog')
    css = Gtk.CssProvider()
    css.load_from_data(b'''
    .recovery-file-dialog {background-color:#121212;}
    .recovery-file-dialog button {background-image:none;background-color:#252525;
      color:#e2e2e2;border:0;border-bottom:0;border-radius:4px;box-shadow:none;}
    .recovery-file-dialog button:active {background-color:#424242;}
    .recovery-file-dialog .recovery-file-title {font-size:1.15em;font-weight:bold;}
    .recovery-file-dialog .recovery-file-name {color:#bdbdbd;}
    ''')
    def walk(widget):
        widget.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 10)
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children(): walk(child)
    walk(dialog)
    dialog._recovery_css = css


class RecoveryFiles:
    def __init__(self, panel):
        self.panel = panel
        self.screen = panel._screen
        self.result = {}
        self.click_pending = False
        self.active = False
        self.generation = 0

    def activate(self):
        self.active = True
        self.refresh()

    def deactivate(self):
        self.active = False
        self.generation += 1
        self.click_pending = False

    def refresh(self):
        generation = self.generation
        def received(reply, *args):
            if generation != self.generation: return
            if 'result' in reply:
                self.result = reply['result']
                self.update_badges()
        self.screen._ws.send_method('printer.lugo_recovery.control', {'action':'status'}, received)

    def decorate(self, child, filename):
        label = getattr(child, '_recovery_name_label', None)
        if label is None: return
        child._recovery_original = label.get_label() if label.get_use_markup() else GLib.markup_escape_text(label.get_text())
        child._recovery_filename = filename
        self.update_badge(child)

    def update_badge(self, child):
        label = getattr(child, '_recovery_name_label', None)
        button = getattr(child, '_recovery_button', None)
        if button is not None:
            from ks_includes.KlippyGtk import find_widget
            label = find_widget(button, Gtk.Label)
        if label is None or not hasattr(child, '_recovery_original'): return
        marker = '<span foreground="#e2c079" weight="bold">!</span>  ' if matches(self.result,child._recovery_filename) else ''
        label.set_markup(marker + child._recovery_original)

    def update_badges(self):
        for child in self.panel.flowbox.get_children():
            self.update_badge(child)

    def select(self, widget, filename):
        if self.click_pending: return
        self.click_pending = True
        self.generation += 1
        generation = self.generation
        def received(reply, *args):
            if generation != self.generation or not self.active: return
            self.click_pending = False
            self.generation += 1
            if 'error' in reply:
                self.error(reply['error'])
                return
            self.result = reply.get('result', {})
            self.update_badges()
            if matches(self.result, filename):
                self.choose(filename, self.result['record']['session'])
            else:
                self.panel.open_print_info(widget, filename)
        sent = self.screen._ws.send_method('printer.lugo_recovery.control', {'action':'status'}, received)
        if not sent:
            self.click_pending = False
            self.error('Check printer connection.')
            return
        def expired():
            if self.click_pending and generation == self.generation:
                self.click_pending = False
                self.generation += 1
                self.error('Check printer connection.')
            return False
        GLib.timeout_add_seconds(8, expired)

    def error(self, error):
        if isinstance(error, dict): error = error.get('message', str(error))
        self.screen.show_popup_message(tr(self.screen, str(error)))

    def dialog(self, title, filename, message, buttons, callback):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, vexpand=True,
                      valign=Gtk.Align.CENTER)
        box.set_margin_start(16)
        box.set_margin_end(16)
        for text, cls in ((title,'recovery-file-title'),(filename,'recovery-file-name'),(message,'')):
            label=Gtk.Label(label=text,wrap=True,justify=Gtk.Justification.CENTER,xalign=.5)
            label.set_max_width_chars(32)
            if cls: label.get_style_context().add_class(cls)
            box.pack_start(label,False,False,0)
        dialog=self.panel._gtk.Dialog(title,buttons,box,callback)
        style_dialog(dialog)
        return dialog

    def choose(self, filename, session):
        def answer(dialog, response):
            self.panel._gtk.remove_dialog(dialog)
            if response == Gtk.ResponseType.OK:
                def verified(reply,*args):
                    result=reply.get('result',{})
                    if matches(result,filename) and result['record']['session']==session:
                        self.screen.show_panel('recovery',tr(self.screen,'Print recovery'))
                    else:
                        self.error('Recovery record changed; reopen the review')
                if not self.screen._ws.send_method('printer.lugo_recovery.control',{'action':'status'},verified):
                    self.error('Check printer connection.')
            elif response == Gtk.ResponseType.REJECT:
                self.confirm_fresh(filename, session)
        self.dialog(tr(self.screen,'Interrupted print found'),filename,
                    tr(self.screen,'Would you like to resume this print?'),[
            {'name':tr(self.screen,'Resume print'),'response':Gtk.ResponseType.OK},
            {'name':tr(self.screen,'Start fresh'),'response':Gtk.ResponseType.REJECT},
            {'name':tr(self.screen,'Close'),'response':Gtk.ResponseType.CANCEL}],answer)

    def confirm_fresh(self, filename, session):
        def answer(dialog, response):
            self.panel._gtk.remove_dialog(dialog)
            if response != Gtk.ResponseType.OK: return
            generation = self.generation
            def discarded(reply,*args):
                if 'error' in reply:
                    self.error(reply['error'])
                    return
                self.result = reply.get('result', {})
                self.update_badges()
                if self.active and generation == self.generation:
                    self.panel.open_print_info(None, filename)
            if not self.screen._ws.send_method('printer.lugo_recovery.control',
                    {'action':'discard','session':session},discarded):
                self.error('Check printer connection.')
        self.dialog(tr(self.screen,'Start fresh'),filename,
                    tr(self.screen,'Delete the interrupted print record and open print options. Printing starts only when you press Print.'),[
            {'name':tr(self.screen,'Start fresh'),'response':Gtk.ResponseType.OK},
            {'name':tr(self.screen,'Cancel'),'response':Gtk.ResponseType.CANCEL}],answer)
