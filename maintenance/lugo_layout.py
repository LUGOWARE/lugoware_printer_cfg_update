"""Language-independent GTK label sizing without truncating menu captions."""
from gi.repository import Gtk, Pango


def wrap_label(label, width_chars=12):
    label.set_line_wrap(True)
    label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    label.set_ellipsize(Pango.EllipsizeMode.NONE)
    label.set_lines(-1)
    # Limit natural width, not allocated width: homogeneous grids can stay narrow.
    label.set_width_chars(1)
    label.set_max_width_chars(width_chars)
    label.set_justify(Gtk.Justification.CENTER)
    label.set_xalign(0.5)
    label.set_yalign(0.5)


def format_button(widget, lines=2):
    from ks_includes.KlippyGtk import find_widget
    label = find_widget(widget, Gtk.Label)
    if label is None:
        return
    if lines > 1:
        wrap_label(label)
    else:
        # Numeric controls and intentionally single-line fields retain their layout.
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_lines(lines)
