"""Run in a GTK session; uses dummy interface names and never connects to NM."""
import sys
from pathlib import Path
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'maintenance'))
from lugo_interface_selector import InterfaceSelector


def settle():
    for _ in range(20):
        for iteration in range(50):
            if not Gtk.events_pending():
                break
            Gtk.main_iteration()
        time.sleep(.01)


window = Gtk.OffscreenWindow()
selector = InterfaceSelector()
selector.append('eth0', 'eth0')
selector.append('wlan0', 'wlan0')
assert selector.set_active_id('wlan0')
changes = []
selector.connect('changed', lambda widget: changes.append(widget.get_active_id()))
window.add(selector)
window.show_all()
selector.clicked()
settle()
assert selector._popup.get_visible(), 'single activation must leave the list open'
assert selector._popup.get_modal(), 'outside clicks must dismiss the popover'
selector._items['eth0'][1].clicked()
settle()
assert changes == ['eth0']
assert not selector._popup.get_visible()
assert selector.get_active_id() == 'eth0'
assert selector.set_active_id('eth0') and changes == ['eth0']
assert not selector.set_active_id('missing')
selector.clicked()
settle()
assert selector._popup.get_visible()
selector._popup.popdown()
settle()
assert not selector._popup.get_visible()
selector.clicked()
settle()
selector.hide()
settle()
assert not selector._popup.get_visible(), 'leaving the panel must dismiss the list'
window.destroy()
print('Tap-open, select-close, modal dismissal and panel-hide checks passed.')
