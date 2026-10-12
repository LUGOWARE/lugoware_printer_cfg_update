"""GTK regression: navigating through long titles must not shrink the header."""
import sys
from pathlib import Path
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from lugo_layout import fit_title


def settle():
    for _ in range(100):
        if not Gtk.events_pending():
            break
        Gtk.main_iteration()


window = Gtk.OffscreenWindow()
label = Gtk.Label()
fit_title(label)
window.add(label)
window.set_default_size(240, 35)
window.show_all()
label.set_text('192.168.0.151')
settle()
baseline = label.create_pango_layout(label.get_text()).get_pixel_size()
for _ in range(5):
    for title in ('FLEX4 Tool temperature control', 'FLEX4 툴별 온도 제어',
                  'FLEX4 工具温度控制', '192.168.0.151'):
        label.set_text(title)
        for width in (50, 160, 240):
            window.resize(width, 35)
            settle()
        assert label.get_layout().get_line_count() == 1
        assert label.get_ellipsize() == Pango.EllipsizeMode.END
    assert label.create_pango_layout(label.get_text()).get_pixel_size() == baseline
    assert not hasattr(label, '_lugo_fit_scale'), 'title must not use caption scaling'
window.destroy()
print('Title size remains constant across navigation and narrow allocations.')
