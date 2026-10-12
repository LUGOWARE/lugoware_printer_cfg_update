"""Tap-open network interface chooser using a modal GTK popover."""
from gi.repository import GObject, Gtk


class InterfaceSelector(Gtk.MenuButton):
    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self):
        super().__init__()
        self._active_id = None
        self._items = {}
        self.set_label('— ▾')
        self.set_hexpand(False)
        self.set_vexpand(False)
        self._popup = Gtk.Popover.new(self)
        self._popup.set_modal(True)
        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._list.set_border_width(6)
        self._popup.add(self._list)
        self.set_popover(self._popup)
        self.connect('unmap', lambda *_: self._popup.popdown())

    def append(self, item_id, text):
        if item_id in self._items:
            raise ValueError('Duplicate interface: '+item_id)
        button = Gtk.Button(label=text)
        button.set_size_request(120, 48)
        button.connect('clicked', self._choose, item_id)
        self._items[item_id] = (text, button)
        self._list.pack_start(button, False, False, 0)
        self._list.show_all()

    def get_active_id(self):
        return self._active_id

    def set_active_id(self, item_id):
        if item_id not in self._items:
            return False
        if item_id == self._active_id:
            return True
        self._active_id = item_id
        self.set_label(self._items[item_id][0]+' ▾')
        for key, (_, button) in self._items.items():
            context = button.get_style_context()
            if key == item_id:
                context.add_class('button_active')
            else:
                context.remove_class('button_active')
        self.emit('changed')
        return True

    def _choose(self, button, item_id):
        self._popup.popdown()
        self.set_active_id(item_id)
