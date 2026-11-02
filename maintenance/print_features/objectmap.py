import logging
import math

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk


class ObjectMap(Gtk.DrawingArea):
    def __init__(self, screen, printer, font_size):
        super().__init__()
        self._screen = screen
        self.set_hexpand(True)
        self.set_vexpand(True)
        # self.get_style_context().add_class('objectmap')
        self.printer = printer
        self.max_length = 0
        self.connect("draw", self.draw_graph)
        self.add_events(Gdk.EventMask.TOUCH_MASK)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button_press_event", self.event_cb)
        self.font_size = round(font_size * 0.75)
        self.font_spacing = round(self.font_size * 1.5)
        self.margin_left = round(self.font_size * 2.75)
        self.margin_right = 15
        self.margin_top = 10
        self.margin_bottom = self.font_size * 2
        self.objects = self.printer.get_stat("exclude_object", "objects")
        self.current_object = self.printer.get_stat("current_object", "current_object")
        self.excluded_objects = self.printer.get_stat("exclude_object", "excluded_objects")
        self.min_x = self.min_y = 99999999
        self.max_x = self.max_y = 0

    def x_graph_to_bed(self, width, gx):
        return (
            ((gx - self.margin_left) * (self.max_x - self.min_x))
            / (width - self.margin_left - self.margin_right)
        ) + self.min_x

    def y_graph_to_bed(self, height, gy):
        return (
            (1 - ((gy - self.margin_top) / (height - self.margin_top - self.margin_bottom)))
            * (self.max_y - self.min_y)
        ) + self.min_y

    def event_cb(self, da, ev):
        # Convert coordinates from screen-graph to bed
        x = self.x_graph_to_bed(da.get_allocated_width(), ev.x)
        y = self.y_graph_to_bed(da.get_allocated_height(), ev.y)
        logging.info(f"Touched GRAPH {ev.x:.0f},{ev.y:.0f} BED: {x:.0f},{y:.0f}")

        excluded = self.printer.get_stat('exclude_object', 'excluded_objects') or []
        for obj in reversed(self.objects):
            polygon = obj.get('polygon', [])
            if self.contains(polygon, x, y):
                if obj['name'] not in excluded:
                    self.exclude_object(obj['name'])
                break

    @staticmethod
    def contains(polygon, x, y):
        inside = False
        for i, (ax, ay) in enumerate(polygon):
            bx, by = polygon[i - 1]
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                inside = not inside
        return inside

    def exclude_object(self, name):
        if hasattr(self, 'exclude_callback'):
            self.exclude_callback(name)
            return
        script = {"script": f"EXCLUDE_OBJECT NAME={name}"}
        self._screen._confirm_send_action(
            None,
            _("Are you sure do you want to exclude the object?") + f"\n\n{name}",
            "printer.gcode.script",
            script,
        )

    def draw_graph(self, da, ctx):
        right = da.get_allocated_width() - self.margin_right
        bottom = da.get_allocated_height() - self.margin_bottom
        self.objects = self.printer.get_stat("exclude_object", "objects")

        self.min_x = self.min_y = float('inf')
        self.max_x = self.max_y = float('-inf')
        for obj in self.objects:
            for point in obj.get("polygon", []):
                # Find min coords
                self.min_x = min(self.min_x, point[0])
                self.min_y = min(self.min_y, point[1])
                # Find max coords
                self.max_x = max(self.max_x, point[0])
                self.max_y = max(self.max_y, point[1])

        if not math.isfinite(self.min_x):
            return
        self.max_x = max(self.max_x, self.min_x + 1.)
        self.max_y = max(self.max_y, self.min_y + 1.)

        # Styling
        ctx.set_source_rgb(0.5, 0.5, 0.5)  # Grey
        ctx.set_line_width(1)
        ctx.set_font_size(self.font_size)

        # Borders
        ctx.move_to(self.margin_left, self.margin_top)
        ctx.line_to(right, self.margin_top)
        ctx.line_to(right, bottom)
        ctx.line_to(self.margin_left, bottom)
        ctx.line_to(self.margin_left, self.margin_top)
        ctx.stroke()

        # Axis labels
        ctx.move_to(0, bottom + self.font_spacing)
        ctx.show_text(f"{self.min_x:.0f},{self.min_y:.0f}")
        ctx.stroke()
        ctx.move_to(right - self.font_spacing * 2, bottom + self.font_spacing)
        ctx.show_text(f"{self.max_x:.0f},{self.min_y:.0f}")
        ctx.stroke()
        ctx.move_to(0, self.font_spacing / 2)
        ctx.show_text(f"{self.min_x:.0f},{self.max_y:.0f}")
        ctx.stroke()

        # middle markers
        midx = (right - self.margin_left) / 2 + self.margin_left
        ctx.set_dash([1, 1])
        ctx.move_to(midx, self.margin_top)
        ctx.line_to(midx, bottom)
        ctx.stroke()
        midy = (self.margin_top - bottom) / 2 + bottom
        ctx.move_to(self.margin_left, midy)
        ctx.line_to(right, midy)
        ctx.stroke()
        ctx.set_dash([1, 0])

        # Draw objects
        for obj in self.objects:
            # change the color depending on the status
            if obj["name"] in (self.printer.get_stat("exclude_object", "excluded_objects") or []):
                ctx.set_source_rgb(.38, .14, .14)
            elif obj["name"] == self.printer.get_stat("exclude_object", "current_object"):
                ctx.set_source_rgb(.15, .65, .85)
            else:
                ctx.set_source_rgb(0.5, 0.5, 0.5)  # Grey
            for i, point in enumerate(obj.get("polygon", [])):
                # Convert coordinates from bed to screen-graph
                x = self.x_bed_to_graph(da.get_allocated_width(), point[0])
                y = self.y_bed_to_graph(da.get_allocated_height(), point[1])
                if i == 0:
                    ctx.move_to(x, y)
                    continue
                ctx.line_to(x, y)
                # logging.info(f"obj graph: {x=:.0f},{y=:.0f} bed: {point[0]:.0f},{point[1]:.0f}")
            ctx.close_path()
            ctx.fill()
            ctx.stroke()

        # Draw numbered badges last, so another polygon cannot hide them.
        for number, obj in enumerate(self.objects, 1):
            polygon = obj.get('polygon', [])
            if not polygon:
                continue
            center = obj.get('center') or [sum(p[i] for p in polygon) / len(polygon) for i in (0, 1)]
            x = self.x_bed_to_graph(da.get_allocated_width(), center[0])
            y = self.y_bed_to_graph(da.get_allocated_height(), center[1])
            excluded = obj['name'] in (self.printer.get_stat('exclude_object', 'excluded_objects') or [])
            radius = max(10, round(self.font_size * .8))
            # Compact rounded tiles matching the dark KlipperScreen controls.
            ctx.new_path()
            corner = 4
            for cx, cy, angle in ((x + radius - corner, y - radius + corner, -math.pi / 2),
                                   (x + radius - corner, y + radius - corner, 0),
                                   (x - radius + corner, y + radius - corner, math.pi / 2),
                                   (x - radius + corner, y - radius + corner, math.pi)):
                ctx.arc(cx, cy, corner, angle, angle + math.pi / 2)
            ctx.close_path()
            ctx.set_source_rgb(.30, .12, .12) if excluded else ctx.set_source_rgb(.14, .14, .14)
            ctx.fill_preserve()
            ctx.set_source_rgb(.65, .28, .28) if excluded else ctx.set_source_rgb(.36, .36, .36)
            ctx.set_line_width(1)
            ctx.stroke()
            ctx.set_source_rgb(.92, .92, .92)
            text = str(number)
            ctx.set_font_size(round(self.font_size * .9))
            xb, yb, w, h, _, _ = ctx.text_extents(text)
            ctx.move_to(x - w / 2 - xb, y - h / 2 - yb)
            ctx.show_text(text)
            if excluded:
                # A visible X next to the number; the object stays on the map.
                ctx.set_source_rgb(1, .3, .3)
                ctx.set_line_width(3)
                ctx.move_to(x + radius + 3, y - 5)
                ctx.line_to(x + radius + 13, y + 5)
                ctx.move_to(x + radius + 3, y + 5)
                ctx.line_to(x + radius + 13, y - 5)
                ctx.stroke()

    def x_bed_to_graph(self, width, bx):
        return (
            ((bx - self.min_x) * (width - self.margin_left - self.margin_right))
            / (self.max_x - self.min_x)
        ) + self.margin_left

    def y_bed_to_graph(self, height, by):
        return (
            (1 - ((by - self.min_y) / (self.max_y - self.min_y)))
            * (height - self.margin_top - self.margin_bottom)
        ) + self.margin_top
