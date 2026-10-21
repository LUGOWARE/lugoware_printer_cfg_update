"""One-way clipped text scrolling, with fixed icons and controls."""
from time import monotonic
from gi.repository import Gtk, Pango, PangoCairo
from ks_includes.KlippyGtk import find_widget


def tick(panel):
    targets = [(find_widget(panel.buttons['elapsed'], Gtk.Label),
                panel.labels['elapsed'].get_text() + ' ', panel._screen.width // 2 - 44)]
    if hasattr(panel, '_toolchange_label'):
        targets.append((find_widget(panel._toolchange_label, Gtk.Label), '', panel._screen.width // 2 - 44))
    if hasattr(panel, '_sensor_label'):
        targets.append((find_widget(panel._sensor_label, Gtk.Label), '', panel._screen.width // 2 - 110))
    for label, prefix, limit in targets:
        if label is None:
            continue
        if not hasattr(label, '_info_scroll'):
            label._info_scroll = {'offset': 0., 'wait': monotonic()+2, 'last': monotonic()}
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_single_line_mode(True)
            label.connect('draw', draw)
        state = label._info_scroll
        state['prefix'] = prefix
        state['limit'] = max(20, limit)
        now = monotonic()
        delta = min(.1, now-state['last'])
        state['last'] = now
        _, body, _, available = layouts(label)
        maximum = max(0, body.get_pixel_size()[0]-available)
        if maximum == 0:
            state['offset'] = 0.
            state['wait'] = now+2
        elif now >= state['wait']:
            if state['offset'] >= maximum:
                state['offset'] = 0.
                state['wait'] = now+2
            else:
                state['offset'] = min(maximum, state['offset']+delta*35)
                if state['offset'] >= maximum:
                    state['wait'] = now+2
        label.queue_draw()


def layouts(label):
    state = label._info_scroll
    prefix = state['prefix']
    value = label.get_text()
    body = value[len(prefix):] if prefix and value.startswith(prefix) else value
    pre = label.create_pango_layout(prefix)
    text = label.create_pango_layout(body)
    pw = pre.get_pixel_size()[0]
    return pre, text, pw, max(1, min(label.get_allocated_width(), state['limit'])-pw)


def draw(label, cr):
    pre, body, pw, available = layouts(label)
    state = label._info_scroll
    color = label.get_style_context().get_color(label.get_state_flags())
    y = (label.get_allocated_height()-body.get_pixel_size()[1])/2
    cr.save()
    cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
    cr.rectangle(0, 0, min(label.get_allocated_width(), state['limit']), label.get_allocated_height())
    cr.clip()
    cr.move_to(0, y)
    PangoCairo.show_layout(cr, pre)
    cr.rectangle(pw, 0, available, label.get_allocated_height())
    cr.clip()
    cr.move_to(pw-state['offset'], y)
    PangoCairo.show_layout(cr, body)
    cr.restore()
    return True

