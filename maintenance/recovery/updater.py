import logging
import threading
from pathlib import Path
from gettext import ngettext

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib

from ks_includes.screen_panel import ScreenPanel
from ks_includes.lugoware_release_notes import read_notes


class Panel(ScreenPanel):
    ALLOWED_UPDATES = frozenset(("lugoware_config", "lugoware_system"))

    def __init__(self, screen, title):
        title = title or _("Update")
        super().__init__(screen, title)
        self.labels = {}
        self.update_status = None

        self.buttons = {
            "refresh": self._gtk.Button(
                image_name="arrow-down",
                label=_("Refresh"),
                style=None,
                scale=self.bts,
                position=Gtk.PositionType.LEFT,
                lines=1,
            ),
        }
        self.buttons["refresh"].connect("clicked", self.refresh_updates)
        self.buttons["refresh"].set_vexpand(False)

        top_box = Gtk.Box(vexpand=False)
        top_box.pack_start(self.buttons["refresh"], True, True, 0)

        self.update_msg = Gtk.Label(label=_("Checking for updates, please wait..."), vexpand=True)

        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.add(self.update_msg)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        self.main_box.pack_start(top_box, False, False, 0)
        self.main_box.pack_start(self.scroll, True, True, 0)

        self.main_box.set_spacing(12)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.css = Gtk.CssProvider()
        self.css.load_from_data(b"""
        .update-card { background-color:#252525; border:0; border-radius:.25em; padding:14px; }
        .update-card button { background-image:none; background-color:#1f1f1f;
          border:1px solid #353535; border-radius:.25em; box-shadow:none; padding:10px; min-height:42px; }
        .update-card button:active { background-color:#424242; }
        .update-card button:disabled { opacity:.5; }
        .update-card .updater-item { font-weight:bold; }
        """)
        self.content.add(self.main_box)

    def activate(self):
        self._screen._ws.send_method("machine.update.status", callback=self.get_updates)

    def text(self, key):
        config = getattr(self._screen, '_config', None)
        lang = config.get_main_config().get('language', 'en') if config else 'en'
        words = {
            'ko': {'current':'현재 버전', 'new':'새 버전', 'changes':'변경 내역', 'version':'버전', 'empty':'등록된 변경 내역이 없습니다.'},
            'zh_CN': {'current':'当前版本', 'new':'新版本', 'changes':'更新内容', 'version':'版本', 'empty':'暂无更新说明。'},
            'zh_TW': {'current':'目前版本', 'new':'新版本', 'changes':'更新內容', 'version':'版本', 'empty':'尚無更新說明。'},
            'ja': {'current':'現在のバージョン', 'new':'新しいバージョン', 'changes':'変更内容', 'version':'バージョン', 'empty':'変更内容は登録されていません。'},
            'en': {'current':'Current version', 'new':'New version', 'changes':'Changes', 'version':'Version', 'empty':'No change notes available.'},
        }
        return words.get(lang, words['en'])[key]

    def style_card(self, widget):
        widget.get_style_context().add_provider(self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                self.style_card(child)

    def create_info_grid(self):
        self.labels = {}
        self.current_notes = {}
        self.expanders = {}
        self.notes_generation = getattr(self, "notes_generation", 0) + 1
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, vexpand=True)
        names = sorted(self.ALLOWED_UPDATES.intersection(self.update_status["version_info"]))
        for prog in names:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, hexpand=True)
            card.get_style_context().add_class("update-card")
            heading = Gtk.Label(label=prog, xalign=0, wrap=True)
            heading.get_style_context().add_class("updater-item")
            card.pack_start(heading, False, False, 0)
            self.labels[prog] = heading
            info = self.update_status["version_info"][prog]
            for kind, version in (("current",info.get("version","?")),("new",info.get("remote_version","?"))):
                expander = Gtk.Expander(label=self.text(kind) + ": " + str(version))
                expander.set_expanded(False)
                note = Gtk.Label(label=self.text("empty"), xalign=0, wrap=True, hexpand=True)
                note.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                note.set_max_width_chars(36)
                note.set_margin_top(12)
                note.set_margin_bottom(8)
                if kind == "current":
                    self.current_notes[prog] = note
                expander.add(note)
                card.pack_start(expander, False, False, 0)
                self.expanders[(prog,kind)] = expander
            controls = Gtk.Box(spacing=10, homogeneous=True)
            self.buttons[f"{prog}_status"] = self._gtk.Button(label=_("Update"), lines=1)
            self.buttons[f"{prog}_status"].connect("clicked", self.show_update_info, prog)
            controls.pack_start(self.buttons[f"{prog}_status"], True, True, 0)
            card.pack_start(controls, False, False, 0)
            rows.pack_start(card, True, True, 0)
            self.update_program_info(prog)
            self.style_card(card)
        if not names:
            rows.pack_start(Gtk.Label(label=_("Not working or not configured"), wrap=True), True, True, 0)
        self.clear_scroll()
        self.scroll.add(rows)
        self.load_current_notes()

    def load_current_notes(self):
        generation = self.notes_generation
        config = getattr(self._screen, '_config', None)
        language = config.get_main_config().get('language', 'en') if config else 'en'
        revisions = {(name,kind):self.update_status['version_info'][name].get(field)
                     for name in self.current_notes
                     for kind,field in (('current','current_hash'),('new','remote_hash'))}
        def worker():
            notes = {}
            cache = {}
            for key, revision in revisions.items():
                name, kind = key
                if (name,revision) not in cache:
                    cache[(name,revision)] = read_notes(Path.home(),name,revision,language)
                notes[key] = cache[(name,revision)]
            GLib.idle_add(self.apply_current_notes,generation,notes)
        threading.Thread(target=worker,daemon=True).start()

    def apply_current_notes(self, generation, notes):
        if generation != self.notes_generation:
            return False
        for key, entry in notes.items():
            expander = self.expanders.get(key)
            if expander is None:
                continue
            expander.get_child().set_text(entry.get('body') or self.text('empty') if entry else self.text('empty'))
            if entry and entry.get('version'):
                expander.set_label(self.text(key[1]) + ': ' + entry['version'])
        return False

    def clear_scroll(self):
        for child in self.scroll.get_children():
            self.scroll.remove(child)

    def refresh_updates(self, widget=None):
        self.clear_scroll()
        self.scroll.add(self.update_msg)
        self._gtk.Button_busy(widget, True)
        logging.info("Sending machine.update.refresh")
        self._screen._ws.send_method("machine.update.refresh", callback=self.get_updates)

    def get_updates(self, response, method, params):
        self._gtk.Button_busy(self.buttons["refresh"], False)
        logging.info(response)
        if not response or "result" not in response:
            self.clear_scroll()
            if response and "error" in response:
                self.scroll.add(
                    Gtk.Label(label=f"Moonraker: {response['error']['message']}", vexpand=True)
                )
            else:
                self.scroll.add(Gtk.Label(label=_("Not working or not configured"), vexpand=True))
        else:
            self.update_status = response["result"]
            self.create_info_grid()
        self.scroll.show_all()

    def show_update_info(self, widget, program):
        if program not in self.ALLOWED_UPDATES or self._printer.state in ("printing", "paused"):
            return

        info = (
            self.update_status["version_info"][program]
            if program in self.update_status["version_info"]
            else {}
        )

        scroll = self._gtk.ScrolledWindow(steppers=False)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if program == "full":
            label.set_markup("<b>" + _("Perform a full upgrade?") + "</b>")
            vbox.add(label)
        elif "configured_type" in info and info["configured_type"] == "git_repo":
            if not info["is_valid"] or info["is_dirty"]:
                label.set_markup(_("Do you want to recover %s?") % program)
                recoverybuttons = [
                    {
                        "name": _("Recover Hard"),
                        "response": Gtk.ResponseType.OK,
                        "style": "dialog-warning",
                    },
                    {
                        "name": _("Recover Soft"),
                        "response": Gtk.ResponseType.APPLY,
                        "style": "dialog-info",
                    },
                    {
                        "name": _("Cancel"),
                        "response": Gtk.ResponseType.CANCEL,
                        "style": "dialog-error",
                    },
                ]
                self._gtk.Dialog(_("Recover"), recoverybuttons, label, self.reset_confirm, program)
                return
            else:
                if info["version"] == info["remote_version"]:
                    return
                label.set_text(program + "\n\n" + self.expanders[(program,"new")].get_child().get_text())
                vbox.add(label)

        elif "package_count" in info:
            label.set_markup(
                (
                    f"<b>{info['package_count']} "
                    + ngettext(
                        "Package will be updated",
                        "Packages will be updated",
                        info["package_count"],
                    )
                    + ":</b>\n"
                )
            )
            label.set_vexpand(False)
            vbox.set_valign(Gtk.Align.CENTER)
            vbox.add(label)
            grid = Gtk.Grid(
                column_homogeneous=True,
                halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
            )
            i = 0
            for j, c in enumerate(info["package_list"]):
                label = Gtk.Label(halign=Gtk.Align.START, ellipsize=Pango.EllipsizeMode.END)
                label.set_markup(f"  {c}  ")
                pos = j % 3
                grid.attach(label, pos, i, 1, 1)
                if pos == 2:
                    i += 1
            vbox.add(grid)
        else:
            label.set_markup(
                "<b>"
                + _("%s will be updated to version") % program.capitalize()
                + f": {info['remote_version']}</b>"
            )
            vbox.add(label)

        scroll.add(vbox)

        buttons = [
            {
                "name": _("Update"),
                "response": Gtk.ResponseType.OK,
                "style": "dialog-info",
            },
            {
                "name": _("Cancel"),
                "response": Gtk.ResponseType.CANCEL,
                "style": "dialog-error",
            },
        ]
        self._gtk.Dialog(_("Update"), buttons, scroll, self.update_confirm, program)

    def update_confirm(self, dialog, response_id, program):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            logging.debug(f"Updating {program}")
            self.update_program(self, program)

    def reset_confirm(self, dialog, response_id, program):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            logging.debug(f"Recovering hard {program}")
            self.reset_repo(self, program, True)
        if response_id == Gtk.ResponseType.APPLY:
            logging.debug(f"Recovering soft {program}")
            self.reset_repo(self, program, False)

    def reset_repo(self, widget, program, hard):
        if program not in self.ALLOWED_UPDATES or self._printer.state in ("printing", "paused"):
            return

        if self._screen.state.updating:
            return
        self._screen.base_panel.show_update_dialog()
        msg = _("Starting recovery for") + f" {program}..."
        self._screen._notification_handler.handle(
            "notify_update_response",
            {"application": {program}, "message": msg, "complete": False},
        )
        logging.info(f"Sending machine.update.recover name: {program} hard: {hard}")
        self._screen._ws.send_method("machine.update.recover", {"name": program, "hard": hard})

    def update_program(self, widget, program):
        if program not in self.ALLOWED_UPDATES or self._printer.state in ("printing", "paused"):
            return

        if self._screen.state.updating or not self.update_status:
            return

        if program in self.update_status["version_info"]:
            info = self.update_status["version_info"][program]
            logging.info(f"program: {info}")
            if (
                "package_count" in info
                and info["package_count"] == 0
                or "version" in info
                and info["version"] == info["remote_version"]
            ):
                return
        self._screen.base_panel.show_update_dialog()
        msg = _("Updating") if program == "full" else _("Starting update for") + f" {program}..."
        self._screen._notification_handler.handle(
            "notify_update_response",
            {"application": {program}, "message": msg, "complete": False},
        )

        if program in ["klipper", "moonraker", "system", "full"]:
            logging.info(f"Sending machine.update.{program}")
            self._screen._ws.send_method(f"machine.update.{program}")
        else:
            logging.info(f"Sending machine.update.client name: {program}")
            self._screen._ws.send_method("machine.update.client", {"name": program})

    def update_program_info(self, p):
        if not self.update_status or p not in self.labels:
            return
        info = self.update_status["version_info"][p]
        local = str(info.get("version", "?"))
        remote = str(info.get("remote_version", "?"))
        if not info.get("is_valid", True) or info.get("is_dirty", False):
            self.buttons[f"{p}_status"].set_label(_("Invalid"))
            self.buttons[f"{p}_status"].set_sensitive(True)
        elif local == remote:
            self._already_updated(p)
        else:
            self._needs_update(p, local, remote)
        if self._printer.state in ("printing", "paused"):
            self.buttons[f"{p}_status"].set_sensitive(False)

    def _already_updated(self, p):
        self.buttons[f"{p}_status"].set_label(_("Up To Date"))
        self.buttons[f"{p}_status"].get_style_context().remove_class("update")
        self.buttons[f"{p}_status"].set_sensitive(False)

    def _needs_update(self, p, local="", remote=""):
        logging.info(f"{p} {local} -> {remote}")
        self.buttons[f"{p}_status"].set_label(_("Update"))
        self.buttons[f"{p}_status"].get_style_context().add_class("update")
        self.buttons[f"{p}_status"].set_sensitive(True)
