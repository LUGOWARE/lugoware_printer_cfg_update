"""Display slicer filament presets and per-filament estimated weights."""
import json
import math


def as_list(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    if value is None or value == '':
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, TypeError):
            pass
        return [part.strip().strip('"') for part in value.split(';')]
    return [value]


def rows(metadata):
    names = as_list(metadata.get('filament_name'))
    weights = as_list(metadata.get('filament_weights'))
    count = max(len(names), len(weights), len(as_list(metadata.get('filament_type'))))
    if count == 1 and not weights:
        weights = as_list(metadata.get('filament_weight_total'))
    result = []
    for index in range(count):
        name = str(names[index]) if index < len(names) and names[index] else '—'
        weight = '—'
        if index < len(weights):
            try:
                value = float(weights[index])
                if math.isfinite(value) and value >= 0:
                    weight = f'{value:.2f}'.rstrip('0').rstrip('.') + ' g'
            except (ValueError, TypeError):
                pass
        result.append((str(index + 1), name, weight))
    return result


def build_table(metadata):
    from gi.repository import Gtk, Pango
    grid = Gtk.Grid(column_spacing=10, row_spacing=8, hexpand=True)
    grid.set_margin_end(16)
    entries = rows(metadata)
    if not entries:
        return grid
    for row, values in enumerate([('#', _('Filament'), _('Material usage')), *entries]):
        for column, value in enumerate(values):
            label = Gtk.Label(label=value, xalign=0 if column != 2 else 1,
                              valign=Gtk.Align.START)
            if column == 1:
                label.set_hexpand(True)
                label.set_line_wrap(True)
                label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                label.set_max_width_chars(24)
            if row == 0:
                attrs = Pango.AttrList()
                attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
                label.set_attributes(attrs)
            grid.attach(label, column, row, 1, 1)
    return grid
