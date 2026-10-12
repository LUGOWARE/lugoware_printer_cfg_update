"""Four-column preparation UI backed by guarded PREPARE_ACTION macros."""

import logging
import math
import time
import unicodedata

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    _tool_provider = None

    def __init__(self, screen, title):
        super().__init__(screen, title or _('Prepare'))
        self.selected_tool = None
        self._timer = None
        self._active = False
        self._generation = 0
        self._pending = False
        self._requested_at = 0
        self._socket = None
        self.tool_buttons = {}
        self.buttons = {}
        self._status = {}
        self._status_time = 0
        self._action_pending = False
        self._sent_action = None
        self._display_pending_tool = None
        self._reported_error = False
        self._confirm_dialog = None
        if Panel._tool_provider is None:
            provider = Gtk.CssProvider()
            provider.load_from_data(b'''
                button.lugo-prepare-tool { border: 2px solid #505050;
                    border-radius: 7px; background-image: none; box-shadow: none; }
                button.lugo-prepare-tool.lugo-selected {
                    background-color: #075d79; border-color: #65dcff; }
                button.lugo-prepare-tool.lugo-selected label {
                    color: #ffffff; font-weight: bold; }
            ''')
            Gtk.StyleContext.add_provider_for_screen(
                self.content.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            Panel._tool_provider = provider

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        layout.set_border_width(4)
        row = Gtk.Grid(column_homogeneous=True, column_spacing=0, vexpand=False)
        for tool in range(4):
            button = self._gtk.Button()
            label = Gtk.Label()
            label.set_markup(f'<span size="x-large">T{tool + 1}</span>')
            button.add(label)
            button.set_vexpand(False)
            button.get_style_context().add_class("horizontal_togglebuttons")
            button.get_style_context().add_class("lugo-prepare-tool")
            row.attach(self._readonly(button), tool, 0, 1, 1)
            self.tool_buttons[tool] = button
        layout.pack_start(row, False, False, 0)

        # Retained internally for diagnostics, omitted from the requested layout.
        for name in ("selected", "mount", "temperature"):
            label = Gtk.Label(xalign=0)
            label.set_line_wrap(True)
            self.labels[name] = label
        actions = Gtk.Grid(column_homogeneous=True, row_homogeneous=False,
                           column_spacing=0, row_spacing=0, vexpand=True)
        tool_actions = Gtk.Grid(column_homogeneous=True, row_homogeneous=True,
                               column_spacing=0, row_spacing=0, vexpand=True)
        for tool in range(4):
            for line, (key, text, style, diameter) in enumerate((
                ("dock", _('Dock'), "color1", None),
                ("park", _('Park'), "color2", None),
                ("prime", _('Prime'), "color3", None),
            )):
                button = self._gtk.Button(style=style)
                label = Gtk.Label()
                label.set_line_wrap(True)
                label.set_justify(Gtk.Justification.CENTER)
                size = "x-large"
                label.set_markup(f'<span size="{size}">{text}</span>')
                button.add(label)
                button.connect("clicked", self._action_clicked, key, tool, diameter)
                self.buttons[(key, tool)] = button
                tool_actions.attach(button, tool, line, 1, 1)
        actions.attach(tool_actions, 0, 0, 4, 3)
        self.nozzle_button = self._gtk.Button("extruder", "— / — ℃", "color1", scale=0.8)
        actions.attach(self._readonly(self.nozzle_button), 0, 3, 2, 1)
        temperature_button = self._gtk.Button("heat-up", _('Temperature'), "color2", scale=0.8)
        temperature_button.connect("clicked", self._open_nozzle_temperature)
        actions.attach(temperature_button, 2, 3, 2, 1)
        for col, diameter in ((0, 1.75), (2, 2.85)):
            button = self._gtk.Button(label=_('{v0}mm Extrude').format(v0=diameter), style="color4")
            button.connect("clicked", self._extrude_current, diameter)
            actions.attach(button, col, 4, 2, 1)
        motor = self._gtk.Button("motor-off", _('Motors Off'), "color2", scale=0.8,
                                 position=Gtk.PositionType.TOP)
        motor.connect("clicked", self._action_clicked, "motor_off", None, None)
        self.buttons["motor_off"] = motor
        actions.attach(motor, 0, 5, 4, 1)
        layout.pack_start(actions, True, True, 0)
        # Do not let the panel's natural height push the shared action bar
        # below the screen. Large fonts can scroll within the content area.
        viewport = self._gtk.ScrolledWindow()
        viewport.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        viewport.set_hexpand(True)
        viewport.set_vexpand(True)
        viewport.add(layout)
        self.content.add(viewport)
        self._indicate_tool(None)
        self._unknown(_('Waiting for status'))

    def _open_nozzle_temperature(self, widget):
        self.menu_item_clicked(widget, {"panel": "nozzle_temperature"})

    @staticmethod
    def _compact_message(message, columns=28):
        text = str(message).strip()
        # Keep the useful macro message, not the lengthy evaluation prefix.
        if "gcode.CommandError:" in text:
            text = text.split("gcode.CommandError:", 1)[1].strip()
        lines = []
        for paragraph in text.splitlines():
            line, width = "", 0
            for char in paragraph:
                size = 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
                if line and width + size > columns:
                    lines.append(line.rstrip())
                    line, width = "", 0
                line += char
                width += size
            if line.strip():
                lines.append(line.strip())
        if len(lines) > 4:
            lines = lines[:3] + [_('See log for details')]
        return "\n".join(lines)

    def _notify(self, message):
        logging.warning("Preparation notice: %s", message)
        self._screen.show_popup_message(self._compact_message(message))

    def _extrude_current(self, widget, diameter):
        # Common extrusion buttons always target the physically reported tool.
        tool = self._status.get("gcode_macro TOOL_STATE", {}).get("active_tool")
        self._action_clicked(widget, "extrude", tool, diameter)

    @staticmethod
    def _readonly(widget):
        # Intercept pointer events without the theme's dimmed disabled appearance.
        widget.set_can_focus(False)
        cover = Gtk.EventBox()
        cover.set_visible_window(False)
        cover.set_above_child(True)
        cover.add(widget)
        return cover

    def _indicate_tool(self, tool):
        self.selected_tool = tool
        for index, button in self.tool_buttons.items():
            context = button.get_style_context()
            if index == tool:
                context.add_class("horizontal_togglebuttons_active")
                context.add_class("lugo-selected")
            else:
                context.remove_class("horizontal_togglebuttons_active")
                context.remove_class("lugo-selected")
        self.labels["selected"].set_text(_('Active tool: T{v0}').format(v0=tool + 1) if tool is not None else _('Active tool: —'))

    def _update_indicator(self):
        state = self._status.get("gcode_macro TOOL_STATE", {})
        prep = self._status.get("gcode_macro PREPARE_STATE", {})
        if self._display_pending_tool is not None:
            self._indicate_tool(self._display_pending_tool)
            return
        active = state.get("active_tool")
        tool = prep.get("last_tool") if prep.get("busy") else active
        self._indicate_tool(int(tool) if type(tool) in (int, float) and tool in range(4) else None)

    def _confirm_transfer(self, action, tool, diameter, source):
        if self._confirm_dialog is not None:
            return
        label = Gtk.Label(label=(_('Move the T{v0} head to station T{v1}.\nCheck that the destination station is empty.\nAfter moving, the head uses the destination tool number.').format(v0=source + 1, v1=tool + 1)))
        label.set_line_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_xalign(0.5)
        label.set_yalign(0.5)
        label.set_hexpand(True)
        label.set_vexpand(True)
        label.set_halign(Gtk.Align.FILL)
        label.set_valign(Gtk.Align.FILL)
        self._confirm_dialog = self._gtk.Dialog(
            _('Confirm empty station'),
            [{'name': _('Confirm'), 'response': Gtk.ResponseType.YES},
             {'name': _('Cancel'), 'response': Gtk.ResponseType.NO}], label,
            self._transfer_response, action, tool, diameter, source)

    def _transfer_response(self, dialog, response, action, tool, diameter, source):
        self._gtk.remove_dialog(dialog)
        self._confirm_dialog = None
        if response != Gtk.ResponseType.YES or not self._active:
            return
        self._screen._ws.send_method('printer.objects.query', {'objects': {
            'webhooks': ['state'], 'print_stats': ['state'], 'idle_timeout': ['state'],
            'gcode_macro TOOL_STATE': None, 'gcode_macro PREPARE_STATE': None,
            'filament_switch_sensor toolhead_sensor': None}},
            self._transfer_checked, action, tool, diameter, source, self._generation)

    def _transfer_checked(self, response, method, params, action, tool, diameter, source, generation):
        if not self._active or generation != self._generation:
            return
        status = response.get('result', {}).get('status', {})
        if status.get('gcode_macro TOOL_STATE', {}).get('active_tool') != source:
            self._notify(_('Mounted tool changed. Check again.'))
            return
        self._status = status
        self._status_time = time.monotonic()
        self._action_clicked(None, action, tool, diameter, confirmed_from=source)

    def _action_clicked(self, widget, action, tool, diameter, confirmed_from=None):
        if self._action_pending and action != "motor_off":
            self._notify(_('Action in progress.\nPlease wait.'))
            return
        if not self._active or time.monotonic() - self._status_time > 5:
            self._notify(_('Status unavailable.\nCheck the connection.'))
            return
        mounted = self._status.get('gcode_macro TOOL_STATE', {}).get('active_tool')
        cross = action in ('park', 'prime') and mounted in range(4) and tool in range(4) and mounted != tool
        warning = self.action_warning(self._status, action, tool, allow_cross=cross)
        if warning:
            self._notify(warning)
            return
        if not self._printer.get_config_section("gcode_macro PREPARE_ACTION"):
            self._notify(_('Install preparation macros,\nthen restart Klipper.'))
            return
        if cross and confirmed_from != mounted:
            self._confirm_transfer(action, tool, diameter, int(mounted))
            return
        command = "EXTRUDE" if action.startswith("extrude") else action.upper()
        script = f"PREPARE_ACTION ACTION={command} TOOL={tool if tool is not None else -1}"
        if diameter is not None:
            script += f" DIAMETER={diameter}"
        if cross:
            script += f" CONFIRM_EMPTY=1 FROM_TOOL={int(mounted)}"
        self._action_pending = True
        self._sent_action = (action, tool)
        try:
            sent = self._screen._ws.send_method("printer.gcode.script", {"script": script}, self._action_done)
            if sent is False:
                self._action_pending = False
                self._unknown(_('Check the connection'))
                self._notify(_('Failed to send command.'))
            elif action in ("dock", "prime", "park"):
                self._display_pending_tool = tool
                self._indicate_tool(tool)
        except Exception:
            logging.exception("Preparation command send failed")
            self._unknown(_('Check command result'))
            self._notify(_('Result unavailable.\nCheck the printer.'))

    def _action_done(self, response, method, params):
        completed = self._sent_action
        self._sent_action = None
        self._action_pending = False
        self._generation += 1
        self._pending = False
        self._unknown(_('Waiting for status update'))
        if "error" in response:
            error = response["error"]
            text = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            self._notify(text)
        elif completed and completed[0] in ("dock", "prime"):
            self._indicate_tool(completed[1])
        if self._active:
            self._poll()
        return False

    @staticmethod
    def extrusion_values(diameter):
        if diameter not in (1.75, 2.85):
            raise ValueError("Unsupported filament diameter")
        ratio = (1.75 / diameter) ** 2
        return 10 * ratio, 5 * ratio

    @staticmethod
    def action_warning(status, action, tool, allow_cross=False):
        if status.get("webhooks", {}).get("state") != "ready":
            return _('Check that the printer is ready.')
        if status.get("print_stats", {}).get("state") in ("printing", "paused"):
            return _('Unavailable while printing\nor paused.')
        if action == "motor_off":
            if status.get("idle_timeout", {}).get("state") not in ("Ready", "Idle"):
                return _('Wait for motion to stop\nbefore disabling motors.')
            return None
        state = status.get("gcode_macro TOOL_STATE", {})
        if state.get("changing"):
            return _('Tool is moving.\nPlease wait.')
        if status.get("gcode_macro PREPARE_STATE", {}).get("busy"):
            return _('Preparation incomplete.\nCheck the printer.')
        mounted = state.get("active_tool")
        detected = status.get("filament_switch_sensor toolhead_sensor", {}).get("filament_detected")
        manual = mounted == -1 and detected is True and action in ("park", "prime")
        if (type(mounted) not in (int, float) or mounted not in (-1, 0, 1, 2, 3)
                or (detected is not (mounted != -1) and not manual)):
            return _('Mount status unknown.\nCheck the tool and sensor.')
        if mounted != -1:
            if action in ("park", "prime") and (tool == mounted or (allow_cross and tool in range(4))):
                return None
            if action.startswith("extrude") and tool == mounted:
                return None
            return _('T{v0} is docked.\nPark T{v1} first.').format(v0=int(mounted) + 1, v1=int(mounted) + 1)
        if action == "park" and not manual:
            return _('No tool is docked.')
        return None

    def _render_mount(self):
        state = self._status.get("gcode_macro TOOL_STATE", {})
        sensor = self._status.get("filament_switch_sensor toolhead_sensor", {})
        if state.get("changing"):
            text = _('Changing tools')
        elif state.get("active_tool") == self.selected_tool and sensor.get("filament_detected") is True:
            text = _('Docked')
        elif state.get("is_parked") == 1 and state.get("parked_tool") == self.selected_tool and state.get("active_tool") != self.selected_tool:
            text = _('Parked')
        else:
            text = _('Unknown')
        self.labels["mount"].set_text(_('Mount status: {v0}').format(v0=text))

    def activate(self):
        self.deactivate()
        self._active = True
        self._unknown(_('Checking status'))
        self._poll()
        self._timer = GLib.timeout_add_seconds(2, self._poll)

    def deactivate(self):
        if self._confirm_dialog is not None:
            self._gtk.remove_dialog(self._confirm_dialog)
            self._confirm_dialog = None
        self._active = False
        self._generation += 1
        self._pending = False
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _unknown(self, message):
        self._status = {}
        self._status_time = 0
        self._display_pending_tool = None
        self._indicate_tool(None)
        self.labels["mount"].set_text(_('Mount status: {v0}').format(v0=message))
        self.labels["temperature"].set_text(_('Nozzle temperature: — / — ℃'))
        self.nozzle_button.set_label("— / — ℃")

    def _poll(self):
        if not self._active:
            return False
        socket = getattr(self._screen, "_ws", None)
        if socket is not self._socket:
            self._socket = socket
            self._generation += 1
            self._pending = False
        if not socket or not getattr(socket, "connected", False):
            self._generation += 1
            self._pending = False
            self._unknown(_('Waiting for printer connection'))
            return True
        if self._pending:
            if time.monotonic() - self._requested_at > 8:
                self._unknown(_('Response delayed; status unavailable'))
            return True

        # Query rather than replacing KlipperScreen's shared subscription.
        # Macro variables are not subscribed on every KlipperScreen version.
        objects = {"webhooks": ["state"]}
        for name, fields in (
            ("gcode_macro PREPARE_STATE", ["busy", "error", "last_tool"]),
            ("idle_timeout", ["state"]),
            ("print_stats", ["state"]),
            ("gcode_macro TOOL_STATE", ["active_tool", "changing", "is_parked", "parked_tool"]),
            ("filament_switch_sensor toolhead_sensor", ["filament_detected", "enabled"]),
            ("extruder", ["temperature", "target"]),
        ):
            if name in ("print_stats", "idle_timeout") or self._printer.get_config_section(name):
                objects[name] = fields
        self._pending = True
        self._requested_at = time.monotonic()
        try:
            sent = socket.send_method(
                "printer.objects.query", {"objects": objects},
                self._status_received, self._generation,
            )
            if sent is False:
                self._pending = False
                self._unknown(_('Status query failed'))
        except Exception:
            logging.exception("Preparation status query failed")
            self._pending = False
            self._unknown(_('Status query failed'))
        return True

    def _status_received(self, response, method, params, generation):
        if not self._active or generation != self._generation:
            return False
        self._pending = False
        status = response.get("result", {}).get("status", {})
        if "error" in response or status.get("webhooks", {}).get("state") != "ready":
            self._unknown(_('Check printer readiness'))
            return False
        self._status = status
        self._status_time = time.monotonic()
        self._update_indicator()
        self._render_mount()
        heater = status.get("extruder", {})
        current = self._temperature(heater.get("temperature"))
        target = self._temperature(heater.get("target"))
        self.labels["temperature"].set_text(_('Nozzle temperature: {v0} / {v1} ℃').format(v0=current, v1=target))
        self.nozzle_button.set_label(f"{current} / {target} ℃")
        prep = status.get("gcode_macro PREPARE_STATE", {})
        error = bool(prep.get("error"))
        if error and not self._reported_error:
            self._notify(_('No nozzle detected.\nCheck the toolhead.'))
        self._reported_error = error
        return False

    @staticmethod
    def _temperature(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return f"{value:.1f}"
        return "—"
