"""Bounded captions: translated text must not enlarge whole-screen grids."""
from gi.repository import Gtk, Pango


def wrap_label(label, width_chars=12, lines=2):
    label.set_line_wrap(True)
    label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    label.set_ellipsize(Pango.EllipsizeMode.END if lines > 0 else Pango.EllipsizeMode.NONE)
    label.set_lines(lines)
    # Limit natural width, not allocated width: homogeneous grids can stay narrow.
    label.set_width_chars(1)
    label.set_max_width_chars(width_chars)
    label.set_justify(Gtk.Justification.CENTER)
    label.set_xalign(0.5)
    label.set_yalign(0.5)


def _fit_caption(label, allocation):
    """Shrink long captions within their allocation, with a readable lower bound."""
    if allocation.width < 10 or allocation.height < 10:
        return
    text = label.get_text()
    key = (text, allocation.width, label.get_lines())
    if getattr(label, '_lugo_fit_key', None) == key:
        return
    label._lugo_fit_key = key
    # Touchscreen taps leave the pointer on a button; automatic tooltips linger.
    label.set_has_tooltip(False)
    probe = label.create_pango_layout(text)
    probe.set_width(allocation.width * Pango.SCALE)
    probe.set_wrap(Pango.WrapMode.WORD_CHAR)
    for scale in (1.0, .95, .9, .85, .8, .75):
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_scale_new(scale))
        probe.set_attributes(attrs)
        if probe.get_line_count() <= max(1, label.get_lines()) and probe.get_pixel_size()[1] <= allocation.height:
            break
    previous_text, previous_scale = getattr(label, '_lugo_fit_scale', (None, 1.0))
    if previous_text == text:
        # Never alternate between two sizes as GTK reallocates the same caption.
        scale = min(scale, previous_scale)
    label._lugo_fit_scale = (text, scale)
    if previous_text == text and scale == previous_scale:
        return
    attrs = label.get_attributes()
    attrs = attrs.copy() if attrs else Pango.AttrList()
    attrs.change(Pango.attr_scale_new(scale))
    label.set_attributes(attrs)


def fit_title(label):
    # A translated title must never increase the shared title bar height.
    label.set_line_wrap(False)
    label.set_lines(1)
    label.set_width_chars(1)
    label.set_max_width_chars(20)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    _connect_fit(label)


def _connect_fit(label):
    if not getattr(label, '_lugo_fit_connected', False):
        label.connect('size-allocate', _fit_caption)
        label.connect('notify::label', lambda widget, prop: _fit_caption(widget, widget.get_allocation()))
        label._lugo_fit_connected = True


def format_button(widget, lines=2):
    from ks_includes.KlippyGtk import find_widget
    label = find_widget(widget, Gtk.Label)
    if label is None:
        return
    if lines > 1:
        wrap_label(label, lines=lines)
        _connect_fit(label)
    else:
        # Numeric controls and intentionally single-line fields retain their layout.
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_lines(lines)
