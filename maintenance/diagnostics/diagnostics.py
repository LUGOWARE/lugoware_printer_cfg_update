"""User-started diagnostics UI. Polling only until the user confirms a test."""
import json
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or _('Diagnostics'))
        self.timer = None
        self.sensor_timer = None
        self.sensor_pending = False
        self.pending = False
        self.state = {}
        self.last_serial = None
        self.buttons = {}
        self.details = {}
        self.result_buttons = {}
        self.progress_bars = {}
        self.progress_labels = {}
        self.names = {'sensor': _('Toolhead sensor test'), 'heater': _('Nozzle heater test'),
                      'motor': _('Motor test'), 'probe': _('Probe test'), 'fan': _('Fan test')}
        self.instructions = {
            'heater': _('Alternately heats the two heaters. Remove the toolhead from the mount and start when the nozzle is below 50°C.'),
            'motor': _('Park and remove the toolhead before this test'),
            'probe': _('Clear the bed and remove the toolhead. After HOME_CHECK, checks deployment 10 times and measures 10 sets of 3 samples at the bed center. Probe speed is unchanged. No mesh or offset is saved.'),
            'fan': _('Please check that the fans are actually running.'),
            'sensor': _('Press and release the switch to view its current state.')}
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.get_style_context().add_class('lugo-diagnostics')
        outer.set_margin_start(8)
        outer.set_margin_end(8)
        self.summary = Gtk.Label(label=_('Checking printer status…'), xalign=0, wrap=True)
        outer.pack_start(self.summary, False, False, 0)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for kind, name in self.names.items():
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.get_style_context().add_class('diagnostic-card')
            head = Gtk.Box(spacing=8)
            head.pack_start(Gtk.Label(label=name, xalign=0), True, True, 0)
            card.pack_start(head, False, False, 0)
            detail = Gtk.Label(label=_('Checking printer status…') if kind == 'sensor' else _('Not tested'), xalign=0, wrap=True)
            if kind == 'sensor':
                detail.set_xalign(1)
                status_row = Gtk.Box(spacing=8)
                self.sensor_indicator = Gtk.Label(label='●')
                self.sensor_indicator.get_style_context().add_class('sensor-indicator')
                self.sensor_indicator.get_style_context().add_class('sensor-unknown')
                status_row.pack_end(detail, False, False, 0)
                status_row.pack_end(self.sensor_indicator, False, False, 0)
                card.pack_start(status_row, False, False, 0)
            else:
                card.pack_start(detail, False, False, 0)
            self.details[kind] = detail
            if kind != 'sensor':
                start = Gtk.Button(label=_('Start test'))
                start.connect('clicked', self.confirm, kind)
                result = Gtk.Button(label=_('View results'))
                result.set_sensitive(False)
                result.connect('clicked', self.show_result, kind)
                controls = Gtk.Box(spacing=8)
                controls.pack_start(start, False, False, 0)
                controls.pack_start(result, False, False, 0)
                head.pack_end(controls, False, False, 0)
                progress = Gtk.ProgressBar()
                progress.set_show_text(False)
                progress.set_fraction(0)
                progress.set_text('0%')
                overlay = Gtk.Overlay()
                overlay.add(progress)
                value_label = Gtk.Label(label='0%')
                value_label.set_halign(Gtk.Align.CENTER)
                value_label.set_valign(Gtk.Align.CENTER)
                value_label.get_style_context().add_class('diagnostic-percent')
                overlay.add_overlay(value_label)
                overlay.set_overlay_pass_through(value_label, True)
                card.pack_start(overlay, False, False, 0)
                self.progress_labels[kind] = value_label
                self.progress_bars[kind] = progress
                self.buttons[kind], self.result_buttons[kind] = start, result
            rows.pack_start(card, False, False, 0)
        scroll = self._gtk.ScrolledWindow()
        scroll.add(rows)
        outer.pack_start(scroll, True, True, 0)
        self.stop_button = Gtk.Button(label=_('Stop test'))
        self.stop_button.connect('clicked', self.stop)
        self.stop_button.set_sensitive(False)
        outer.pack_end(self.stop_button, False, False, 0)
        css = Gtk.CssProvider()
        css.load_from_data(b'\n            .lugo-diagnostics .diagnostic-card { background-color: #252525;\n                border: 0; border-radius: .25em; padding: 10px; }\n            .lugo-diagnostics button { background-image: none; background-color: #252525;\n                border: 1px solid #252525; border-radius: .25em; padding: 8px;\n                box-shadow: none; }\n            .lugo-diagnostics button:active { background-color: #424242; }\n            .lugo-diagnostics .diagnostic-percent { color: #e2e2e2; font-weight: bold;\n                text-shadow: 0 1px 2px #000000; }\n            .lugo-diagnostics .sensor-indicator { font-size: 1.35em; }\n            .lugo-diagnostics .sensor-off { color: #000000; }\n            .lugo-diagnostics .sensor-on { color: #2196f3; }\n            .lugo-diagnostics .sensor-unknown { color: #888888; }\n            .lugo-diagnostics button:disabled { color: #888888; }\n            .lugo-diagnostics progressbar trough { min-height: 30px;\n                background-color: #1c1c1c; border-radius: .25em; }\n            .lugo-diagnostics progressbar progress { min-height: 30px;\n                background-color: #2f5631; border-radius: .25em; }\n        \n.fan_controls button,\n.fine-card button,\n.lugo-temperature-control button,\n.lugo-diagnostics .diagnostic-card button,\n.lugo-theme .frame-item button,\n.lugo-theme .tz-current button,\n.lugo-settings .frame-item button { background-color: #1f1f1f; }\n.fan_controls button:active,\n.fan_controls button:checked,\n.fan_controls button.selected,\n.fan_controls button.lugo-selected,\n.fan_controls button.button_active,\n.fan_controls button.lugo-tapped,\n.fine-card button:active,\n.fine-card button:checked,\n.fine-card button.selected,\n.fine-card button.lugo-selected,\n.fine-card button.button_active,\n.fine-card button.lugo-tapped,\n.lugo-temperature-control button:active,\n.lugo-temperature-control button:checked,\n.lugo-temperature-control button.selected,\n.lugo-temperature-control button.lugo-selected,\n.lugo-temperature-control button.button_active,\n.lugo-temperature-control button.lugo-tapped,\n.lugo-diagnostics .diagnostic-card button:active,\n.lugo-diagnostics .diagnostic-card button:checked,\n.lugo-diagnostics .diagnostic-card button.selected,\n.lugo-diagnostics .diagnostic-card button.lugo-selected,\n.lugo-diagnostics .diagnostic-card button.button_active,\n.lugo-diagnostics .diagnostic-card button.lugo-tapped,\n.lugo-theme .frame-item button:active,\n.lugo-theme .frame-item button:checked,\n.lugo-theme .frame-item button.selected,\n.lugo-theme .frame-item button.lugo-selected,\n.lugo-theme .frame-item button.button_active,\n.lugo-theme .frame-item button.lugo-tapped,\n.lugo-theme .tz-current button:active,\n.lugo-theme .tz-current button:checked,\n.lugo-theme .tz-current button.selected,\n.lugo-theme .tz-current button.lugo-selected,\n.lugo-theme .tz-current button.button_active,\n.lugo-theme .tz-current button.lugo-tapped,\n.lugo-settings .frame-item button:active,\n.lugo-settings .frame-item button:checked,\n.lugo-settings .frame-item button.selected,\n.lugo-settings .frame-item button.lugo-selected,\n.lugo-settings .frame-item button.button_active,\n.lugo-settings .frame-item button.lugo-tapped,\n.lugo-extrusion button.lugo-inner-control:active,\n.lugo-extrusion button.lugo-inner-control:checked,\n.lugo-extrusion button.lugo-inner-control.selected,\n.lugo-extrusion button.lugo-inner-control.lugo-selected,\n.lugo-extrusion button.lugo-inner-control.button_active,\n.lugo-extrusion button.lugo-inner-control.lugo-tapped { background-color: #424242; }\n')
        def style(widget):
            widget.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_USER+1)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    style(child)
        style(outer)
        self.content.add(outer)

    def dialog(self, title, body, callback=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.pack_start(Gtk.Label(label=title, wrap=True), False, False, 0)
        label = Gtk.Label(label=body, wrap=True, xalign=.5, yalign=.5,
                          justify=Gtk.Justification.CENTER, hexpand=True, vexpand=True)
        scroll = self._gtk.ScrolledWindow()
        scroll.add(label)
        box.pack_start(scroll, True, True, 0)
        buttons = [{'name': _('Start test'), 'response': Gtk.ResponseType.OK, 'style': 'diagnostic-confirm'},
                   {'name': _('Cancel'), 'response': Gtk.ResponseType.CANCEL, 'style': 'diagnostic-confirm'}] if callback else [
                       {'name': _('Confirm'), 'response': Gtk.ResponseType.CLOSE, 'style': 'diagnostic-confirm'}]
        def answer(dialog, response):
            self._gtk.remove_dialog(dialog)
            if callback and response == Gtk.ResponseType.OK:
                callback()
        popup = self._gtk.Dialog(title, buttons, box, answer)
        if callback:
            self.neutral_confirm(popup, Gtk.ResponseType.OK)
            self.neutral_confirm(popup, Gtk.ResponseType.CANCEL)
        else:
            self.neutral_confirm(popup)

    def neutral_confirm(self, popup, response=Gtk.ResponseType.CLOSE):
        button = popup.get_widget_for_response(response)
        css = Gtk.CssProvider()
        css.load_from_data(b'''
            button.diagnostic-confirm, button.diagnostic-confirm:focus {
                background-image: none; background-color: #252525;
                border: 0; border-image: none; border-radius: .25em;
                box-shadow: none; }
            button.diagnostic-confirm:active { background-color: #424242;
                border: 0; box-shadow: none; }
        ''')
        button.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 10)

    def confirm(self, button, kind):
        self.dialog(self.names[kind], self.instructions[kind], lambda: self.request('start', kind))

    def request(self, action='status', kind=None):
        if self.pending and action == 'status':
            return True
        params = {'action': action}
        if kind:
            params['kind'] = kind
        if action == 'start':
            for button in self.buttons.values():
                button.set_sensitive(False)
        self.pending = True
        sent = self._screen._ws.send_method('printer.lugo_diagnostics.control', params,
                                           self.response, action)
        if sent is False:
            self.pending = False
            self.summary.set_text(_('Check printer connection.'))
        return True

    def response(self, response, method=None, params=None, action='status'):
        self.pending = False
        if 'error' in response:
            error = response['error']
            message = error.get('message', str(error)) if isinstance(error, dict) else str(error)
            self.summary.set_text(_(message))
            if action != 'status':
                self.dialog(_('Check printer readiness'), _(message))
            return
        self.state = response.get('result', {})
        active = self.state.get('active', False)
        self.summary.set_text((_('Test running') + f" · {self.state.get('elapsed', 0):.0f}s")
                              if active else _('Select a test. Each test requires confirmation.'))
        for kind, button in self.buttons.items():
            button.set_sensitive(not active)
            result = self.state.get('results', {}).get(kind)
            self.result_buttons[kind].set_sensitive(bool(result))
            self.details[kind].set_text((_('Last test date') + ': ' + result.get('timestamp', '—')) if result else _('Not tested'))
        kind = self.state.get('kind')
        data = self.state.get('data', {})
        sensor = self.state.get('toolhead_sensor')
        self.update_sensor(sensor)
        if active and kind in self.details:
            phase = self.state.get('phase')
            text = _('Test running')
            activity = ''
            if kind == 'heater':
                activity = _('Cooling heaters') if phase == 'heater_cooling' else (
                    _('Heating H2') if data.get('stage') == 3 else _('Heating H1'))
            elif kind == 'probe':
                activity = (_('Deployment check') + f" {data.get('deployment_cycles',0)}/10"
                            if data.get('schema') == 4 and data.get('activity') == 'deployment' else
                            _('Measurements') + f" {data.get('sets',0)}/10 × 3" if data.get('schema') == 4 else
                            _('Measurements') + f" {len(data.get('samples', []))}/10")
            elif kind == 'motor':
                segment = data.get('segment', 0)
                labels = {'position':_('Positioning'), 'x':_('X-axis motion'), 'y':_('Y-axis motion'),
                          'diagonal_a':_('Diagonal motion'), 'diagonal_b':_('Diagonal motion'),
                          'z_down':_('Z-axis motion') + ' ↓', 'z_up':_('Z-axis motion') + ' ↑', 'z_finish':_('Z-axis motion') + ' ↕', 'z_repeat':_('Z-axis motion') + ' ↕'}
                labels['ellipse'] = _('Motor test - circular')
                for corner in range(1,5):
                    labels['infill_'+str(corner)] = _('Diagonal motion') + f' {corner}/4'
                activity = labels.get(data.get('activity'), _('Positioning'))
                if str(data.get('activity','')).startswith('infill_'):
                    activity += f" · {data.get('cycle',0)}/50"
                if data.get('activity') == 'z_repeat':
                    activity += f" {data.get('cycle',0)}/20"
                if data.get('activity') in ('x','y','diagonal_a','diagonal_b','ellipse'):
                    activity += f" {data.get('cycle',0)}/5"
            elif kind == 'fan':
                if phase == 'fan_heating':
                    activity = _('Heating nozzle to 50°C')
                elif phase == 'fan_nozzle':
                    activity = _('Nozzle fan check (5 s)')
                else:
                    activity = (_('Part cooling fan') if data.get('stage', 1) == 1 else _('Chamber filter fan'))
                    activity += f" {data.get('percent', 0)}%"
            if activity:
                text += ' - ' + activity
            if phase == 'homing':
                text = _('Checking home position…')
            self.details[kind].set_text(text)
        for test_kind, bar in self.progress_bars.items():
            running = active and kind == test_kind
            record = self.state.get('results', {}).get(test_kind, {})
            values = data if running else record.get('data', {})
            elapsed = self.state.get('elapsed', 0) if running else record.get('duration', 0)
            phase = self.state.get('phase', '') if running else ''
            percent = self.test_progress(test_kind, values, elapsed, phase)
            if not running and record.get('outcome') in ('passed', 'warning', 'review'):
                percent = 100
            elif not running and test_kind == 'heater' and 'result2' in values:
                percent = 100
            if running:
                percent = min(99, percent)
            bar.set_fraction(percent / 100.)
            self.progress_labels[test_kind].set_text(f'{percent}%')
        self.stop_button.set_sensitive(active)
        result = self.state.get('result', {})
        serial = result.get('serial')
        if self.last_serial is None:
            self.last_serial = serial or 0
        elif serial and serial != self.last_serial:
            self.last_serial = serial
            self.show_result(None, result['kind'])

    @staticmethod
    def test_progress(kind, data, elapsed, phase):
        # Stage completion, not an estimate of remaining wall-clock time.
        if phase == 'homing' or not data:
            return 0
        if kind == 'heater':
            value = elapsed / 32. * 100
        elif kind == 'probe':
            value = (data.get('deployment_cycles',0)*2 + data.get('sets',0)*8
                     if data.get('schema') == 4 else len(data.get('samples', []))*10)
        elif kind == 'motor':
            value = data.get('segment', 0) / max(1, data.get('segments',14)) * 100
        elif kind == 'fan':
            completed = data.get('completed', [])
            if 'nozzle' in completed:
                value = 100
            elif phase == 'fan_nozzle':
                value = 95
            elif phase == 'fan_heating' or 'chamber' in completed:
                value = 80
            else:
                value = (40 if data.get('stage', 1) == 2 else 0) + data.get('percent', 0) * .4
        else:
            value = 0
        return max(0, min(100, int(value)))

    def outcome(self, value):
        return {'passed': _('Within test reference'), 'review': _('Visual check required'),
                'warning': _('Outside test reference'), 'failed': _('Test failed'),
                'stopped': _('Test stopped')}.get(value, _('Not tested'))

    def result_content(self, kind, result):
        data = result.get('data', {})
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.get_style_context().add_class('diagnostic-results')
        root.set_margin_start(8)
        root.set_margin_end(8)
        root.set_margin_top(10)
        root.set_margin_bottom(10)
        root.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label=self.names[kind], wrap=True, justify=Gtk.Justification.CENTER)
        title.get_style_context().add_class('result-status')
        title.get_style_context().add_class('result-' + result.get('outcome', 'review'))
        root.pack_start(title, False, False, 0)

        def card(title=None):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.get_style_context().add_class('result-card')
            if title:
                label = Gtk.Label(label=title, xalign=0, wrap=True)
                label.get_style_context().add_class('result-heading')
                box.pack_start(label, False, False, 0)
            root.pack_start(box, False, False, 0)
            return box

        def row(box, title, value, emphasis=False):
            line = Gtk.Box(spacing=12)
            label = Gtk.Label(label=title, xalign=0, wrap=True)
            label.set_hexpand(True)
            val = Gtk.Label(label=str(value), xalign=1, wrap=True)
            val.set_justify(Gtk.Justification.RIGHT)
            val.set_max_width_chars(22)
            if emphasis:
                val.get_style_context().add_class('result-value')
            line.pack_start(label, True, True, 0)
            line.pack_end(val, False, False, 0)
            box.pack_start(line, False, False, 0)

        def note(box, text):
            label = Gtk.Label(label=text, xalign=0, wrap=True)
            label.get_style_context().add_class('result-note')
            box.pack_start(label, False, False, 0)

        if kind == 'heater':
            grades = {'normal': _('Normal operation'), 'degraded': _('Suspected heater degradation'),
                      'fault': _('Heater fault')}
            for number in (1, 2):
                box = card()
                delta = data.get(f'delta{number}')
                row(box, f'H{number}', f'{delta:+.2f} °C' if delta is not None else '—', True)
                grade = grades.get(data.get(f'result{number}'), _('Previous criteria')
                                  if delta is not None and not data.get('schema') else _('Not tested'))
                note(box, grade)
        elif kind == 'probe':
            if data.get('schema') == 4:
                box = card(_('Deployment check'))
                row(box, _('Deployment signal OK'), f"{data.get('deployment_cycles',0)} / 10")
                row(box, _('Deployment errors'), str(data.get('deployment_errors',0)))
                row(box, _('Measurements'), f"{data.get('sets',0)} / 10 × 3")
                note(box, _('Signal checks do not prove mechanical retraction.'))
                box = card(_('Errors and retries'))
                for key,title in [('trigger_errors',_('Trigger errors')),
                                  ('tolerance_errors',_('Tolerance errors')),
                                  ('tolerance_retries',_('Measurement retries')),
                                  ('reactivations',_('Recovery redeployments')),
                                  ('recoveries',_('Recovered measurements'))]:
                    row(box,title,str(data.get(key,0)))
            if 'spread' in data:
                box=card(_('Measurements'))
                row(box,_('Range'),f"{data['spread']:.5f} mm",True)
                row(box,_('Standard deviation'),f"{data['stddev']:.5f} mm")
                for key,title in [('minimum',_('Minimum')),('maximum',_('Maximum')),('mean',_('Average'))]:
                    row(box,title,f'{data[key]:.5f} mm')
                details=Gtk.Expander(label=_('Measurement details'))
                samples=Gtk.Label(label='\n'.join(f'{i+1:02d}    {v:.5f} mm' for i,v in enumerate(data.get('samples',[]))),xalign=0)
                details.add(samples)
                box.pack_start(details,False,False,0)
            note(card(),_('Reference range: 0.030 mm. Repeatability does not guarantee bed leveling accuracy.'))
        elif kind == 'motor':
            if data.get('model'):
                box = card('FLEX4 ' + data['model'])
                row(box, 'XY', '500 mm/s · 16000 mm/s²')
                row(box, 'Z', f"{data.get('z_speed',40):g} mm/s · {data.get('z_accel',0):g} mm/s²")
            for name, values in data.get('after', {}).items():
                driver, axis = name.split(maxsplit=1)
                box = card(axis.replace('stepper_', '').upper() + ' · ' + driver.upper())
                for key, label in [('run_current', _('Configured run current')),
                                   ('hold_current', _('Configured hold current'))]:
                    current = values.get(key)
                    row(box, label, f'{current:.2f} A' if current is not None else _('Unavailable'))
                for snapshot, title in [('before', _('Before test')), ('after', _('After test'))]:
                    state = data.get(snapshot, {}).get(name, {}).get('drv_status')
                    section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                    details = Gtk.Expander(label=title)
                    details.set_expanded(False)
                    if isinstance(state, dict):
                        row(section, _('Drive mode'), _('Quiet mode') if state.get('stealth') else _('SpreadCycle'))
                        row(section, _('Motor state'), _('Stopped') if state.get('stst') else _('Moving'))
                        if 'cs_actual' in state:
                            row(section, _('Current control scale'), str(state['cs_actual']) + ' / 31')
                        for bits, label in [(('otpw',), _('Overheat warning')),
                                            (('ot',), _('Overheat shutdown')),
                                            (('s2ga','s2gb'), _('Short to ground')),
                                            (('s2vsa','s2vsb'), _('Short to supply'))]:
                            row(section, label, _('Detected') if any(state.get(k, 0) for k in bits)
                                else _('No flag in snapshot'))
                    else:
                        note(section, _('Unavailable'))
                    details.add(section)
                    box.pack_start(details, False, False, 0)
            guidance = card()
            note(guidance, _('These are snapshots before and after the test, not continuous monitoring.'))
            note(guidance, _('Displayed current is configured current, not measured current.'))
            note(guidance, _('Check for noise during movement and whether it occurs at a particular position.'))
        elif kind == 'fan':
            for key, title in [('part', _('Part cooling fan')),
                               ('chamber', _('Chamber filter fan')),
                               ('nozzle', _('Nozzle cooling fan'))]:
                box = card(title)
                if data.get('schema') == 3:
                    row(box, '50°C · 5 s' if key == 'nozzle' else '0 → 100% · 10% / 2 s',
                        '✓' if key in data.get('completed', []) else '—')
                else:
                    states = [o.get(key, {}) for o in data.get('observations', [])]
                    speeds = sorted({round(v.get('speed', 0)*100) for v in states})
                    row(box, _('Fan test'), ' / '.join(str(v)+'%' for v in speeds) or '—')
            note(card(), _('Please check that the fans are actually running.'))

        meta = card()
        row(meta, _('Duration'), f"{result.get('duration', 0):.1f} s")
        row(meta, _('Last test date'), result.get('timestamp', '—'))
        if kind == 'heater':
            rules = card(_('Assessment criteria'))
            note(rules, _('Temperature rise after 10 seconds of heating'))
            row(rules, '≥ 7°C', _('Normal operation'))
            row(rules, '5°C ~ < 7°C', _('Suspected heater degradation'))
            row(rules, '< 5°C', _('Heater fault'))
            if not data.get('schema'):
                note(rules, _('This record used the previous criteria. Run a new test for the updated assessment.'))
        message = result.get('message', '')
        if result.get('outcome') in ('failed', 'stopped') and message != 'Heater test complete':
            note(card(), _(message))
        if data.get('cleanup_errors'):
            note(card(), _('Restoration failed. Check heater, fan and sensor states before use.'))

        css = Gtk.CssProvider()
        css.load_from_data(b'''
            .diagnostic-results .result-card { background-color: #252525;
                border: 0; border-radius: .25em; padding: 10px 12px; }
            .diagnostic-results label { color: #e2e2e2; }
            .diagnostic-results .result-status { font-size: 1.15em; font-weight: bold; padding: 6px; }
            .diagnostic-results .result-passed { color: #9bc59b; }
            .diagnostic-results .result-warning, .diagnostic-results .result-review { color: #d9bb85; }
            .diagnostic-results .result-failed { color: #df9999; }
            .diagnostic-results .result-value { font-size: 1.2em; font-weight: bold; }
            .diagnostic-results .result-heading { font-weight: bold; }
            .diagnostic-results .result-note { color: #bcbcbc; }
        ''')
        def style(widget):
            widget.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():style(child)
        style(root)
        scroll = self._gtk.ScrolledWindow()
        scroll.add(root)
        return scroll

    def show_result(self, button, kind):
        result = self.state.get('results', {}).get(kind)
        if not result:
            return
        content = self.result_content(kind, result)
        buttons = [{'name': _('Confirm'), 'response': Gtk.ResponseType.CLOSE, 'style': 'diagnostic-confirm'}]
        def close(dialog, response):
            self._gtk.remove_dialog(dialog)
        popup = self._gtk.Dialog(self.names[kind], buttons, content, close)
        self.neutral_confirm(popup)

    def stop(self, button=None):
        self.summary.set_text(_('Stopping after the current move or probe sample…'))
        self.request('stop')

    def activate(self):
        self.pending = False
        self.request()
        if self.timer is None:
            self.timer = GLib.timeout_add_seconds(1, self.request)
        self.sensor_pending = False
        if self.sensor_timer is None:
            self.sensor_timer = GLib.timeout_add(250, self.poll_sensor)

    def poll_sensor(self):
        if not self.sensor_pending:
            self.sensor_pending = True
            sent = self._screen._ws.send_method('printer.lugo_diagnostics.control',
                {'action': 'sensor'}, self.sensor_response)
            if sent is False:
                self.sensor_pending = False
        return True

    def sensor_response(self, response, *args):
        self.sensor_pending = False
        value = response.get('result', {}).get('detected')
        self.update_sensor(value)

    def update_sensor(self, value):
        self.details['sensor'].set_text(_('Detected') if value is True else _('Not detected')
                                       if value is False else _('Toolhead sensor unavailable'))
        context = self.sensor_indicator.get_style_context()
        for name in ('sensor-on', 'sensor-off', 'sensor-unknown'):
            context.remove_class(name)
        context.add_class('sensor-on' if value is True else 'sensor-off' if value is False else 'sensor-unknown')

    def deactivate(self):
        if self.state.get('active'):
            self.request('stop')
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        if self.sensor_timer is not None:
            GLib.source_remove(self.sensor_timer)
            self.sensor_timer = None
