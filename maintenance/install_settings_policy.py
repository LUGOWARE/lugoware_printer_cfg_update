"""Apply the appliance's supported KlipperScreen settings without changing language."""
import os
import re
import shutil
from pathlib import Path


BLOCK = '''        # Appliance settings policy: keep hidden options available for config saving.
        fixed_settings = {"theme": "material-darker", "show_cursor": "False", "enable_addons": "False"}
        hidden_settings = {"only_heaters", "auto_open_extrude", "use_dpms", "screensaver_wake_delay"}
        for item in self.configurable_options:
            for name, option in item.items():
                if name in fixed_settings:
                    option["type"] = None
                    option["value"] = fixed_settings[name]
                elif name in hidden_settings:
                    option["type"] = None
                elif name == "font_size":
                    option["value"] = "medium"
                    option["options"] = [choice for choice in option["options"]
                                         if choice["value"] in ("small", "medium", "large")]
        if not self.config.has_section("main"):
            self.config.add_section("main")
        for name, value in fixed_settings.items():
            self.config.set("main", name, value)
        if self.config.get("main", "font_size", fallback="medium") not in ("small", "medium", "large"):
            self.config.set("main", "font_size", "medium")

'''


def patch(source):
    if BLOCK in source:
        return source
    anchor = '        # Migrate old side_macro_shortcut to side_shortcut_target\n'
    source = re.sub(r'        # Appliance settings policy:.*?(?=        # Migrate old side_macro_shortcut)',
                    '', source, flags=re.S)
    if source.count(anchor) != 1:
        raise ValueError('Unsupported KlipperScreen configuration structure')
    result = source.replace(anchor, BLOCK + anchor)
    compile(result, 'config.py', 'exec')
    return result


def patch_settings(source):
    anchor = '        self.labels["settings_menu"] = self._gtk.ScrolledWindow()'
    line = '        options = [item for item in options if "printers" not in item]\n'
    if line in source:
        return source
    if source.count(anchor) != 1:
        raise ValueError('Unsupported settings panel structure')
    result = source.replace(anchor, line + anchor)
    compile(result, 'settings.py', 'exec')
    return result


if __name__ == '__main__':
    screen = Path(os.environ.get('KLIPPERSCREEN_DIR', Path.home() / 'KlipperScreen'))
    changes = {}
    for relative, transform in [('ks_includes/config.py', patch), ('panels/settings.py', patch_settings)]:
        target = screen / relative
        before = target.read_text(encoding='utf-8')
        after = transform(before)
        if before != after:
            changes[target] = (relative, after)
    for target, (relative, after) in changes.items():
        backup = Path(os.environ['BACKUP_DIR']) / 'settings-policy' / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(target, backup)
        target.write_text(after, encoding='utf-8')
    print('Settings policy installed: three font sizes, darker theme, cursor/add-ons disabled.')
