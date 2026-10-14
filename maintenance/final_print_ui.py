"""Idempotent pause-state display and printer-message routing patches."""
def once(text, old, new):
    if new in text:
        return text
    if text.count(old) != 1:
        raise ValueError('Unsupported KlipperScreen source: ' + old)
    return text.replace(old, new, 1)


def job_status(text):
    old = '                self.labels["lcdmessage"].set_label(f"{data[\'display_status\'][\'message\']}")'
    new = ('                from ks_includes.lugo_i18n import translate_text\n'
           '                self.labels["lcdmessage"].set_label(translate_text(str(data["display_status"]["message"])))')
    progress_line = '                self.labels["lcdmessage"].set_label(_lugo_print_message(str(data["display_status"]["message"]), self.state, self.progress, translate_text))'
    if progress_line not in text:
        text = once(text, old, new)
    for name in ('pause', 'resume'):
        anchor = f'            self.enable_button("{name}", "cancel")\n'
        # Only alter the state-display method, not a cancel-dialog callback.
        start = text.index('    def show_buttons_for_state(self):')
        before, block = text[:start], text[start:]
        code = (f'            self._gtk.Button_busy(self.buttons["{name}"], False)\n'
                f'            self.buttons["{name}"].set_opacity(1.0)\n')
        if code not in block:
            block = once(block, anchor, anchor + code)
        text = before + block
    original = '                self.labels["lcdmessage"].set_label(translate_text(str(data["display_status"]["message"])))'
    text = once(text, original, progress_line)
    text = once(text, '        if self.state == "printing":\n            self.buttons["button_grid"].attach(self.buttons["pause"], 0, 0, 1, 1)', '        if self.state == "printing":\n            # A cancelled job\'s detached button can retain its disabled rendering.\n            old_pause = self.buttons["pause"]\n            self.buttons["pause"] = self._gtk.Button("pause", _("Pause"), "color1")\n            self.buttons["pause"].connect("clicked", self.pause)\n            old_pause.destroy()\n            self.buttons["button_grid"].attach(self.buttons["pause"], 0, 0, 1, 1)')
    if 'def _lugo_print_message(' not in text:
        text += PRINT_MESSAGE_HELPER
    return text


def notification(text):
    text = text.replace('LUGO_DOCK_FAILED_PAUSED', 'FAST_CANCEL_DOCK_FAILED_PAUSED')
    if 'FAST_CANCEL_DOCK_FAILED_PAUSED' in text:
        return text
    # This explicit marker is an ordinary // response, not a generic error.
    import re
    match = re.search(r'^    def _gcode_response\(self, data\):\n', text, re.M)
    if not match:
        raise ValueError('Unsupported notification handler')
    code = ('        if data.strip() == "// FAST_CANCEL_DOCK_FAILED_PAUSED":\n'
            '            self._screen.show_popup_message("Tool-head is not in position.", 3)\n'
            '            return True\n')
    return text[:match.end()] + code + text[match.end():]


def popup(text):
    text = text.replace('LUGO_DOCK_FAILED_PAUSED', 'FAST_CANCEL_DOCK_FAILED_PAUSED')
    marker = '        # Final print controls: localize the dock-failure payload.\n'
    if marker in text:
        return text
    anchor = '    def show_popup_message(self, message, level=3, from_ws=False):\n'
    return once(text, anchor, anchor + marker +
                '        if str(message).strip() == "FAST_CANCEL_DOCK_FAILED_PAUSED":\n'
                '            message = "Tool-head is not in position."\n')


PRINT_MESSAGE_HELPER = '\ndef _lugo_print_message(message, state, progress, translate):\n    """Keep explicit heating/mesh/error text; qualify M73 percentage messages."""\n    import re\n    value = message.strip()\n    if state == "printing":\n        if re.fullmatch(r"\\d{1,3}%", value):\n            return translate("PRINTING...") + " " + value\n        if value == "PRINTING...":\n            percent = max(0, min(100, int(progress * 100)))\n            return translate(value) + f" {percent}%"\n    return translate(message)\n'


def temperature(text):
    """Avoid portrait grid expansion caused by full-size +/- images."""
    text = once(text, 'self._gtk.Button("increase", None, "color1")', 'self._gtk.Button("increase", None, "color1", self.bts if self._screen.vertical_mode else None)')
    text = once(text, 'self._gtk.Button("decrease", None, "color3")', 'self._gtk.Button("decrease", None, "color3", self.bts if self._screen.vertical_mode else None)')
    return text
