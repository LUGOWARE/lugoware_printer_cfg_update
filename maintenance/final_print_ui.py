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
