"""Patch the file confirmation dialog without altering printer or G-code data."""
import os
import shutil
from pathlib import Path


def patch(source):
    if '# Filament details table' in source:
        return fit_preview(source)
    start = source.index('        if "filament_type" in fileinfo or "filament_name" in fileinfo:')
    end = source.index('        if "nozzle_diameter" in fileinfo:', start)
    source = source[:start] + source[end:]
    old = '        inside_box.pack_start(info_box, True, True, 0)'
    new = '''        # Filament details table: wrap names, keep dialog buttons visible.
        from ks_includes.filament_details import build_table
        info_box.pack_start(build_table(fileinfo_data), False, False, 8)
        fileinfo.set_ellipsize(Pango.EllipsizeMode.NONE)
        fileinfo.set_line_wrap(True)
        fileinfo.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        fileinfo.set_max_width_chars(36)
        fileinfo.set_xalign(0)
        info_box.set_child_packing(fileinfo, False, False, 0, Gtk.PackType.START)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(int(height))
        scroll.set_max_content_height(int(height))
        scroll.add(info_box)
        inside_box.pack_start(scroll, True, True, 0)'''
    if source.count(old) != 1:
        raise ValueError('Unsupported file dialog layout')
    source = source.replace(old, new)
    compile(source, 'gcodes.py', 'exec')
    return fit_preview(source)


def fit_preview(source):
    # File lists show date/size via get_info_str; only append the estimate here.
    list_start = source.index('    def get_file_info(self, path):')
    list_end = source.index('    def get_file_info_extended(', list_start)
    source = source[:list_start] + '''    def get_file_info(self, path):
        fileinfo = self._screen.files.get_file_info(path)
        if "estimated_time" in fileinfo:
            return _("Estimated Time") + f": <b>{self.format_time(fileinfo['estimated_time'])}</b>"
        return ""

''' + source[list_end:]
    # Let metadata use its natural height and give the remaining space to the image.
    source = source.replace('            ) * 0.30\n', '            ) * 0.45\n')
    source = source.replace('        info_height = int(height * 7 / 3) if self._screen.vertical_mode else int(height)\n', '')
    source = source.replace('        scroll.set_min_content_height(int(height))\n'
                            '        scroll.set_max_content_height(int(height))',
                            '        scroll.set_min_content_height(info_height)\n'
                            '        scroll.set_max_content_height(info_height)')
    anchor = '        scroll.set_min_content_height(info_height)'
    if '# Fit metadata to its content' not in source:
        source = source.replace(anchor, '''        # Fit metadata to its content instead of reserving an empty lower area.
        info_box.show_all()
        if self._screen.vertical_mode:
            natural_height = info_box.get_preferred_height_for_width(int(self._screen.width - 24))[1]
            info_height = min(natural_height + 8, int(height * 11 / 9))
        else:
            info_height = int(height)
''' + anchor)
    source = source.replace('        inside_box.pack_start(scroll, True, True, 0)',
                            '        scroll.set_vexpand(not self._screen.vertical_mode)\n'
                            '        inside_box.pack_start(scroll, not self._screen.vertical_mode, True, 0)')
    table_anchor = '        info_box.pack_start(build_table(fileinfo_data), False, False, 8)\n'
    if '        info_box.reorder_child(fileinfo, -1)' not in source:
        source = source.replace(table_anchor, table_anchor + '        info_box.reorder_child(fileinfo, -1)\n')
    if '        fileinfo.set_margin_top(int(self._gtk.font_size))' not in source:
        source = source.replace('        info_box.reorder_child(fileinfo, -1)\n',
                                '        info_box.reorder_child(fileinfo, -1)\n'
                                '        fileinfo.set_margin_top(int(self._gtk.font_size))\n')
    image_anchor = '        inside_box.pack_start(image_button, True, True, 0)\n'
    if '        inside_box.reorder_child(image_button, 0)' not in source:
        source = source.replace(image_anchor, image_anchor + '        inside_box.reorder_child(image_button, 0)\n')
    compile(source, 'gcodes.py', 'exec')
    return source


if __name__ == '__main__':
    screen = Path(os.environ.get('KLIPPERSCREEN_DIR', Path.home() / 'KlipperScreen'))
    target = screen / 'panels/gcodes.py'
    result = patch(target.read_text(encoding='utf-8'))
    backup = Path(os.environ['BACKUP_DIR']) / 'filament-details'
    backup.mkdir(parents=True, exist_ok=True)
    if not (backup / 'gcodes.py').exists():
        shutil.copy2(target, backup / 'gcodes.py')
    target.write_text(result, encoding='utf-8')
    shutil.copy2(Path(__file__).with_name('filament_details.py'), screen / 'ks_includes/filament_details.py')
