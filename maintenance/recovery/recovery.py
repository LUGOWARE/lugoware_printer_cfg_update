"""Recovery review UI; setup only after checks and explicit final confirmation."""
import gettext
from datetime import datetime
from gi.repository import Gtk, GLib
from ks_includes.screen_panel import ScreenPanel

KO = {
 'Last observed machine Z (estimated)': '마지막 관측 Z 높이 (추정)',
 'Automatic restart layer': '자동 복구 레이어',
 'Automatic restart print Z': '자동 복구 Z 높이',
 'Observed Z is a machine coordinate; restart Z is a print coordinate.': '관측 Z: 기계 좌표 · 복구 Z: 출력 좌표',
 'No matching restart layer in the original file.': '원본 파일에서 재개 레이어를 찾을 수 없습니다.',
 'The mounted head has been removed and parked in its station': '장착된 툴헤드를 제거해 해당 거치대에 놓았습니다.',
 'The print will resume.': '출력을 재개합니다.',
 'The saved recovery record will be discarded.': '저장된 복구 기록을 폐기합니다.',
 'Discard': '폐기',
 'No usable observed machine position is saved.': '자동 복원에 사용할 기계 위치 기록이 없습니다.',
 'Confirm unchanged bed height, parked head and clear paths.': '베드 높이 유지, 툴헤드 거치, 이동 경로를 모두 확인해주세요.',
 'Automatic machine Z estimate': '자동 복원 기계 Z (추정)',
 'Position recorded': '위치 기록 시각',
 'Position record interval': '위치 저장 간격',
 'Resumes from the latest point confirmed executed. Some sections may be printed again.': '이동 실행이 확인된 가장 최근 지점부터 재개합니다. 일부 구간은 중복 출력될 수 있습니다.',
 'Homing XY…': 'XY 홈 이동 중…', 'Heating…': '예열 중…',
 'Docking and priming…': '툴 도킹·프라임 중…',
 'Returning to the print…': '출력 위치로 복귀 중…',
 'Nozzle': '노즐', 'Bed': '베드',
 'Interruption cause': '중단 원인',
 'Last recorded tool state': '마지막으로 확인된 툴 상태',
 'Nozzle temperature sensor out of range (ADC out of range)': '노즐 온도센서 범위 오류 (ADC out of range)',
 'Temperature sensor out of range (ADC out of range)': '온도센서 범위 오류 (ADC out of range)',
 'MCU shutdown': 'MCU 종료 (상세 원인 기록 없음)',
 'Host restarted before print completion': '출력 완료 전 시스템 재시작 (정확한 원인 확인 불가)',
 'Would you like to resume this print?': '이어서 재개하시겠습니까?',
 'Start fresh': '새로 출력',
 'Close': '닫기', 'Cancel': '취소',
 'Delete the interrupted print record and open print options. Printing starts only when you press Print.': '중단 기록을 삭제하고 새 출력 정보창을 엽니다.\n출력 버튼을 눌러야 시작됩니다.',
 'Review the saved layer and machine position before resuming.': '저장된 레이어와 실제 기계 위치를 확인한 뒤 복구해주세요.',
 'Check the actual printer state before starting recovery.': '실제 상태를 확인한 뒤 복구를 시작해 주세요.',
 'Estimated layer at last observation': '마지막 관측 레이어 (추정)',
 'Suggested restart layer': '권장 재시작 레이어',
 'Current physical machine Z (mm)': '현재 실제 기계 Z 높이 (mm)',
 'Enter a verified height, not the model height.': '확인한 기계 좌표를 입력하세요. 출력물 높이가 아닙니다.',
 'The XY homing and docking paths are clear': 'XY 홈·툴 도킹 경로에 장애물이 없습니다',
 'Partial material at/above the restart layer has been removed': '재시작 레이어부터 남은 부분 출력물을 제거했습니다',
 'Prepare recovery': '출력 재개',
 'Resume print': '출력 재개',
 'Recovery will lower the bed for clearance, home XY only, heat, dock and prime the saved tool, then resume.': '베드를 내려 공간 확보 → XY 홈 → 예열 → 저장된 툴 도킹·프라임 → 이어 출력을 실행합니다. Z 홈은 하지 않습니다.',
 'No execution-confirmed checkpoint. This older record cannot resume automatically.': '이전 방식의 기록이라 실행 확인된 재개 지점이 없습니다. 이 기록으로는 이어 출력을 실행할 수 없습니다. 새 출력부터 새 기록이 생성됩니다.',
 'Checking original print file…': '원본 파일과 레이어 분석 중…',
 'Park/remove the mounted head manually before recovery. No tool must be detected.': '먼저 장착된 툴헤드를 수동으로 제거해 거치대에 놓아주세요. 툴이 감지되면 복구를 시작하지 않습니다.',
 'Excluded-object recovery is not enabled in this trial.': '이번 시험 버전은 개체 제외된 출력의 복구를 지원하지 않습니다.',
 'Tool change was not complete at this checkpoint.': '이 지점의 툴 교환이 완료되지 않았습니다.',
 'Docking state is not suitable for recovery.': '이 지점의 도킹 상태로는 복구할 수 없습니다.',
 'Unsupported coordinate state.': '복구할 수 없는 좌표 상태입니다.',
 'Checkpoint has no restorable mesh.': '이 지점에 복원할 메쉬가 없습니다.',
 'Checkpoint temperature is not suitable for recovery.': '복구 온도가 허용 범위가 아닙니다.',
 'Printer configuration changed since this print.': '출력 당시와 프린터 설정이 다릅니다.',
 'Original print file has changed': '원본 출력 파일이 변경되었습니다.',
 'Current physical Z is outside the safe recovery range.': '입력한 실제 Z 높이가 안전 복구 범위를 벗어납니다.',
 'Confirm the bed height, clear path and partial-layer removal.': '베드 높이, 이동 경로, 부분 출력물 제거를 확인해주세요.',
 'Enter a valid physical Z height.': '확인한 실제 기계 Z 높이를 숫자로 입력해주세요.',
 'Recovery approval expired; review again.': '복구 승인이 만료되었습니다. 다시 확인해주세요.',
 'Recovery setup is running.': '복구 준비 동작 중입니다.',
 'Stop recovery': '복구 준비 중단',
 'Recovery preparation cancelled': '복구 준비를 중단했습니다.',
 'Print recovery': '중단 출력 복구', 'Interrupted print found': '중단된 출력 기록이 있습니다',
 'Review recovery': '복구 기록 확인', 'Later': '나중에', 'Discard record': '복구 기록 폐기',
 'No interrupted print record': '복구할 중단 출력 기록이 없습니다',
 'Checking recovery record…': '복구 기록 확인 중…',
 'File': '파일', 'Last recorded layer': '마지막 기록 레이어', 'Recorded Z': '기록된 Z',
 'Recorded tool': '기록된 툴', 'Docking state': '도킹 상태', 'Saved': '기록 시각',
 'Unknown': '확인 불가', 'No tool': '툴 없음', 'Actual mounted tool': '현재 실제 장착 툴',
 'Last fully completed layer': '마지막으로 완전히 출력된 레이어',
 'The bed height has not changed since interruption': '중단 후 베드 높이가 바뀌지 않았습니다',
 'Save recovery checks': '복구 확인 내용 저장',
 'Review saved. No movement or heating was started.': '확인 내용을 저장했습니다. 이동·가열은 실행하지 않았습니다.',
 'Stage 1: records and review only. Motion recovery is not enabled yet.': '1단계: 기록과 확인 기능입니다. 실제 출력 재개는 아직 연결하지 않았습니다.',
 'Recorded positions are observations, not a confirmed stopping point.': '중단 전에 저장된 기록 좌표는 관측값이며 정확한 정지 지점을 보장하지 않습니다.',
 'Delete this recovery candidate? The original G-code is kept.': '복구 대상으로 표시하지 않을까요? 원본 출력 파일은 유지됩니다.',
 'Check printer connection.': '프린터 연결을 확인해주세요.',
 'Recovery review requires an idle printer': '출력 중에는 복구 확인 내용을 변경할 수 없습니다.',
 'Recovery record changed; reopen the review': '복구 기록이 바뀌었습니다. 화면을 다시 열어주세요.',
 'Selected tool does not match the toolhead detection sensor': '선택한 툴 장착 여부와 툴헤드 감지 센서 상태가 다릅니다.',
 'Z position must be checked before recovery': '복구 전에 베드 높이 유지 여부를 확인해주세요.',
 'Unsupported file or missing record': '기록 또는 원본 파일을 확인할 수 없습니다.',
 'docked': '도킹 완료', 'docking': '도킹 중', 'parking': '파킹 중', 'empty': '툴 미장착',
 'normal': '일반 출력', 'idle': '대기',
 'priming': '프라임 중',
}


def tr(screen, text):
    lang = screen._config.get_main_config().get('language', 'en')
    return KO.get(text, gettext.gettext(text)) if lang.startswith('ko') else gettext.gettext(text)


def recovery_details(record):
    reason = record.get('shutdown_detail') or record.get('reason') or 'Unknown'
    if 'ADC out of range' in reason:
        reason = ('Nozzle temperature sensor out of range (ADC out of range)'
                  if "Sensor 'extruder'" in reason else 'Temperature sensor out of range (ADC out of range)')
    # A checkpoint is older than the last observation; do not call it the
    # interruption-time state when shutdown has already replaced that state.
    phase = record.get('snapshot', {}).get('fast_cancel', {}).get('phase')
    if phase not in ('docked', 'docking', 'parking', 'empty', 'normal', 'idle', 'priming'):
        phase = 'Unknown'
    return reason, phase


def center_text(widget):
    if isinstance(widget, Gtk.Label):
        widget.set_xalign(.5)
        widget.set_justify(Gtk.Justification.CENTER)
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            center_text(child)


def centered_message(text):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                  valign=Gtk.Align.CENTER, vexpand=True)
    box.set_margin_start(24)
    box.set_margin_end(24)
    label = Gtk.Label(label=text, wrap=True, xalign=.5,
                      justify=Gtk.Justification.CENTER)
    label.set_max_width_chars(30)
    box.pack_start(label, False, False, 0)
    return box


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or tr(screen, 'Print recovery'))
        self.record = {}
        self.pending = False
        self.proposal_data = {}
        self.render_key = None
        self.timer = None
        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.root.set_border_width(10)
        self.status_label = Gtk.Label(label=tr(screen, 'Checking recovery record…'), wrap=True, xalign=0)
        self.root.pack_start(self.status_label, False, False, 0)
        self.stop_button = Gtk.Button(label=tr(screen, 'Stop recovery'))
        self.stop_button.connect('clicked', lambda button: self.request('abort'))
        self.stop_button.set_no_show_all(True)
        self.root.pack_start(self.stop_button, False, False, 0)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.body.set_valign(Gtk.Align.START)
        self.body.set_margin_start(8)
        self.body.set_margin_end(8)
        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.body)
        self.root.pack_start(scroll, True, True, 0)
        self.content.add(self.root)
        self.request()

    def activate(self):
        if self.timer is None: self.timer = GLib.timeout_add_seconds(2, self.poll)

    def deactivate(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def poll(self):
        self.request()
        return True

    def request(self, action='status', **params):
        if self.pending and action != 'abort':
            return
        self.pending = True
        if action != 'status':
            params['session'] = self.record.get('session', '')
        params['action'] = action
        if self.render_key is None:
            self.status_label.set_text(tr(self._screen, 'Checking recovery record…'))
        if not self._screen._ws.send_method('printer.lugo_recovery.control', params, self.response, action):
            self.pending = False
            self.status_label.set_text(tr(self._screen, 'Check printer connection.'))

    def response(self, response, method=None, params=None, action='status'):
        self.pending = False
        if 'error' in response:
            error = response['error']
            self.status_label.set_text(tr(self._screen, error.get('message', str(error))))
            return
        data = response.get('result', {})
        if action == 'abort':
            self.status_label.set_text(tr(self._screen, 'Recovery preparation cancelled'))
            return
        self.stop_button.set_visible(bool(data.get('state', {}).get('recovering')))
        if action == 'prepare':
            self.confirm_resume(data)
            return
        key = (data.get('record', {}).get('session'), str(data.get('proposal', {})),
               data.get('state', {}).get('available'), bool(data.get('state', {}).get('recovering')))
        # Background polling must not erase validation errors, change layout,
        # or reset the user's height/tool selections while reviewing.
        if action == 'status' and key == self.render_key:
            return
        self.record = data.get('record', {})
        self.proposal_data = data.get('proposal', {})
        if action == 'review':
            self.status_label.set_text(tr(self._screen, 'Review saved. No movement or heating was started.'))
        else:
            self.status_label.set_text(tr(self._screen, 'Recovery setup is running.' if data.get('state', {}).get('recovering') else 'Check the actual printer state before starting recovery.'))
        if key != self.render_key:
            self.render_key = key
            self.render(data.get('state', {}).get('available', False))

    def render(self, available):
        for child in self.body.get_children():
            self.body.remove(child)
        if not available:
            self.body.pack_start(Gtk.Label(label=tr(self._screen, 'No interrupted print record'), wrap=True), False, False, 0)
            self.body.show_all()
            return
        snap = self.record.get('snapshot', {})
        stats = snap.get('print_stats', {})
        pos = snap.get('gcode_move', {}).get('gcode_position') or []
        tool = snap.get('gcode_macro TOOL_STATE', {}).get('active_tool')
        unknown = tr(self._screen, 'Unknown')
        stop = self.proposal_data.get('estimated_stop') or {}
        interruption, tool_state = recovery_details(self.record)
        values = [('File', self.record.get('filename', unknown)),
                  ('Saved', datetime.fromtimestamp(snap.get('recorded_at', self.record.get('started_at', 0))).strftime('%Y-%m-%d %H:%M:%S')),
                  ('Position recorded', datetime.fromtimestamp(stop['recorded_at']).strftime('%H:%M:%S') if stop.get('recorded_at') else unknown),
                  ('Position record interval', f"{stop.get('save_interval', 1):g} s"),
                  ('Recorded tool', f'T{tool+1}' if isinstance(tool, int) and 0 <= tool <= 3 else tr(self._screen, 'No tool') if tool == -1 else unknown),
                  ('Interruption cause', tr(self._screen, interruption)),
                  ('Last recorded tool state', tr(self._screen, tool_state))]
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.get_style_context().add_class('recovery-card')
        for key, value in values:
            if key == 'Interruption cause':
                continue
            row = Gtk.Box(spacing=12)
            label = Gtk.Label(label=tr(self._screen, key), wrap=True, xalign=0, hexpand=True)
            val = Gtk.Label(label=str(value), wrap=True, xalign=1, justify=Gtk.Justification.RIGHT)
            val.set_max_width_chars(20)
            row.pack_start(label, True, True, 0)
            row.pack_end(val, False, False, 0)
            card.pack_start(row, False, False, 0)
        self.body.pack_start(card, False, False, 0)
        cause = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cause.get_style_context().add_class('recovery-card')
        heading = Gtk.Label(label=tr(self._screen, 'Interruption cause'), xalign=0)
        heading.get_style_context().add_class('recovery-heading')
        cause.pack_start(heading, False, False, 0)
        cause.pack_start(Gtk.Label(label=tr(self._screen, interruption), wrap=True, xalign=0), False, False, 0)
        self.body.pack_start(cause, False, False, 0)
        positions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        positions.get_style_context().add_class('recovery-card')
        row = Gtk.Box(spacing=12)
        row.pack_start(Gtk.Label(label=tr(self._screen, 'Estimated layer at last observation'), wrap=True, xalign=0), True, True, 0)
        row.pack_end(Gtk.Label(label=str((self.proposal_data.get('observed') or {}).get('layer', unknown)), xalign=1), False, False, 0)
        positions.pack_start(row, False, False, 0)
        zrow = Gtk.Box(spacing=12)
        zrow.pack_start(Gtk.Label(label=tr(self._screen, 'Last observed machine Z (estimated)'), wrap=True, xalign=0), True, True, 0)
        zvalue = f"{stop['z']:.3f} mm" if stop.get('z') is not None else unknown
        zrow.pack_end(Gtk.Label(label=zvalue, xalign=1), False, False, 0)
        positions.pack_start(zrow, False, False, 0)
        self.body.pack_start(positions, False, False, 0)
        self.body.pack_start(Gtk.Label(label=tr(self._screen, 'Resumes from the latest point confirmed executed. Some sections may be printed again.'), wrap=True, xalign=0), False, False, 0)
        reason = self.proposal_data.get('reason')
        if reason and not self.proposal_data.get('can_prepare'):
            self.body.pack_start(Gtk.Label(label=tr(self._screen, reason), wrap=True, xalign=0), False, False, 0)
        checks = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        checks.get_style_context().add_class('recovery-card')
        self.body.pack_start(checks, False, False, 0)
        self.zcheck = Gtk.CheckButton.new_with_label(tr(self._screen, 'The bed height has not changed since interruption'))
        self.zcheck.get_child().set_line_wrap(True)
        checks.pack_start(self.zcheck, False, False, 0)
        self.pathcheck = Gtk.CheckButton.new_with_label(tr(self._screen, 'The XY homing and docking paths are clear'))
        self.headcheck = Gtk.CheckButton.new_with_label(tr(self._screen, 'The mounted head has been removed and parked in its station'))
        for check in (self.headcheck, self.pathcheck):
            check.get_child().set_line_wrap(True)
            checks.pack_start(check, False, False, 0)
        save = Gtk.Button(label=tr(self._screen, 'Prepare recovery'))
        save.set_sensitive(False)
        self.save_button = save
        for check in (self.zcheck, self.headcheck, self.pathcheck):
            check.connect('toggled', self.update_ready)
        save.connect('clicked', self.save)
        self.body.pack_start(save, False, False, 0)
        discard = Gtk.Button(label=tr(self._screen, 'Discard record'))
        discard.connect('clicked', self.discard)
        self.body.pack_start(discard, False, False, 0)
        from ks_includes.recovery_files import style_dialog
        style_dialog(self.root)
        self.root.get_style_context().add_class('recovery-results')
        css = Gtk.CssProvider()
        css.load_from_data(b'''
          .recovery-results .recovery-card {background-color:#252525;
            border:0;border-radius:.25em;padding:10px 12px;}
          .recovery-results .recovery-heading {font-weight:bold;}
          .recovery-results label {color:#e2e2e2;}
        ''')
        def style(widget):
            widget.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 11)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children(): style(child)
        style(self.root)
        self.body.show_all()

    def update_ready(self, *args):
        self.save_button.set_sensitive(bool(self.proposal_data.get('can_prepare')) and
            all(c.get_active() for c in (self.zcheck, self.headcheck, self.pathcheck)))

    def save(self, button):
        checks = all(c.get_active() for c in (self.zcheck, self.headcheck, self.pathcheck))
        if checks:
            self.request('prepare', checks=1)

    def confirm_resume(self, data):
        label = centered_message(tr(self._screen, 'The print will resume.'))
        def answer(dialog, response):
            self._gtk.remove_dialog(dialog)
            if response == Gtk.ResponseType.OK:
                token = data.get('token', '')
                import re
                if not re.fullmatch('[0-9a-f]{32}', token): return
                def completed(reply, *args):
                    if 'error' in reply:
                        self._screen.show_popup_message(tr(self._screen, reply['error'].get('message', str(reply['error']))))
                if self._screen._ws.send_method('printer.gcode.script', {'script': 'LUGO_RECOVERY_RESUME TOKEN=' + token}, completed):
                    self._screen.show_panel('recovery_progress', tr(self._screen, 'Print recovery'))
        dialog = self._gtk.Dialog(tr(self._screen, 'Resume print'), [
            {'name': _('Cancel'), 'response': Gtk.ResponseType.CANCEL},
            {'name': tr(self._screen, 'Resume print'), 'response': Gtk.ResponseType.OK}], label, answer)
        from ks_includes.recovery_files import style_dialog
        style_dialog(dialog)

    def discard(self, button):
        label = centered_message(tr(self._screen, 'The saved recovery record will be discarded.'))
        def answer(dialog, response):
            self._gtk.remove_dialog(dialog)
            if response == Gtk.ResponseType.OK: self.request('discard')
        dialog = self._gtk.Dialog(tr(self._screen, 'Discard record'), [
            {'name': _('Cancel'), 'response': Gtk.ResponseType.CANCEL},
            {'name': tr(self._screen, 'Discard'), 'response': Gtk.ResponseType.OK}], label, answer)
        from ks_includes.recovery_files import style_dialog
        style_dialog(dialog)
