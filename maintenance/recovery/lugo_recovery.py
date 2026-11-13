""".151 journal with execution-timed layer checkpoints and supervised recovery."""
import copy
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import queue
import threading
import time
import uuid
import subprocess
import sys
import tempfile
try:
    from . import recovery_latency as latency
except ImportError:
    import recovery_latency as latency
from collections import deque
try:
    from .recovery_index import analyze, locate, MARKER, CURA, validate_checkpoint
    from .recovery_execution import RecoveryExecution
    from .recovery_eta import remaining_at, estimate
except ImportError:
    from recovery_index import analyze, locate, MARKER, CURA, validate_checkpoint
    from recovery_execution import RecoveryExecution
    from recovery_eta import remaining_at, estimate

TERMINAL = ('completed', 'cancelled', 'discarded')


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))
    if os.name != 'nt':
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def read_record(path):
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('session'), str):
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


def candidate(data, boot):
    return bool(data and data.get('status') not in TERMINAL and
                (data.get('boot') != boot or data.get('status') == 'interrupted'))


class Recovery(RecoveryExecution):
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        latency.start()
        self.io_latency = latency
        self.boot = uuid.uuid4().hex
        self.folder = Path.home() / 'printer_data/recovery'
        self.path = self.folder / 'current.json'
        self.record = read_record(self.path)
        self.running = False
        self.last_save = 0.
        self.last_pose_save = 0.
        self.last_layer = None
        self.last_checkpoint_capture = 0.
        self.last_submit = 0.
        self.write_error = ''
        self.execution_pending = deque(maxlen=8)
        self.file_layer = 0
        self.retract_debt = 0.
        self.analysis = None
        self.resume_token = None
        self.recovering = False
        self.abort_requested = False
        self.eta_context = None
        self.eta_armed = False
        self.pending = queue.Queue(maxsize=1)
        self.io_lock = threading.Lock()
        self.deleted_sessions = set()
        self.last_written = None
        self.archived_states = set()
        self.missing_sources = {}
        self.writer = threading.Thread(target=self.write_loop, daemon=True)
        self.writer.start()
        self.printer.register_event_handler('klippy:ready', self.ready)
        self.printer.register_event_handler('klippy:shutdown', self.shutdown)
        self.printer.lookup_object('webhooks').register_endpoint('lugo_recovery/control', self.control)
        self.printer.lookup_object('gcode').register_command('LUGO_RECOVERY_RESUME', self.resume_command)

    def ready(self):
        self.config_signature_ready = self.config_hash()
        self.reactor.register_timer(self.cleanup_missing_sources, self.reactor.monotonic() + 5.)
        if hasattr(self, 'execution_pending'):
            self.install_observer()
        if candidate(self.record, self.boot):
            self.record['status'] = 'interrupted'
            self.record.setdefault('reason', 'Host restarted before print completion')
            self.submit()
        stats = self.printer.lookup_object('print_stats')
        for name, outcome in (('note_complete', 'completed'), ('note_cancel', 'cancelled'), ('note_error', 'interrupted')):
            original = getattr(stats, name)
            def terminal(*args, _original=original, _outcome=outcome, **kwargs):
                result = _original(*args, **kwargs)
                try:
                    if self.record and self.record.get('boot') == self.boot:
                        # An explicit error must survive any subsequent cleanup cancellation.
                        if self.record.get('status') != 'interrupted' or _outcome == 'interrupted':
                            self.record['status'] = _outcome
                        self.record['ended_at'] = time.time()
                        if args and _outcome == 'interrupted': self.record['reason'] = str(args[0])
                        self.running = False
                        self.submit()
                except Exception:
                    logging.exception('Recovery terminal record failed')
                return result
            setattr(stats, name, terminal)
        self.reactor.register_timer(self.tick, self.reactor.monotonic() + 1.)

    def install_observer(self):
        gcode = self.printer.lookup_object('gcode')
        original_wait = gcode.register_command('TEMPERATURE_WAIT', None)
        def wait(cmd):
            if not self.recovering: return original_wait(cmd)
            name = cmd.get('SENSOR')
            sensor = self.printer.lookup_object('heaters').heaters.get(name)
            if sensor is None: raise cmd.error('Recovery heater is unavailable')
            low = cmd.get_float('MINIMUM', float('-inf'))
            high = cmd.get_float('MAXIMUM', float('inf'))
            deadline = self.reactor.monotonic() + 600
            while True:
                self.check_recovery_abort()
                now = self.reactor.monotonic()
                value, target = sensor.get_temp(now)
                if target <= 0 or now > deadline: raise cmd.error('Recovery heating stopped or timed out')
                if low <= value <= high: return
                self.printer.lookup_object('toolhead').get_last_move_time()
                self.reactor.pause(now + .1)
        gcode.register_command('TEMPERATURE_WAIT', wait)
        original_process = gcode._process_commands
        def process(commands, need_ack=True):
            if not self.recovering: return original_process(commands, need_ack)
            def checked():
                for command in commands:
                    self.check_recovery_abort()
                    yield command
            return original_process(checked(), need_ack)
        gcode._process_commands = process
        original = gcode.run_script
        sd = self.printer.lookup_object('virtual_sdcard')
        depth = [0]
        gm = self.printer.lookup_object('gcode_move')
        def observe(script):
            outer = sd.is_cmd_from_sd() and not depth[0] and not self.recovering
            depth[0] += 1
            try:
                try:
                    if outer and (MARKER.match(script.strip()) or CURA.match(script.strip())):
                        self.observe_layer(sd)
                    elif outer and script.strip().upper().startswith('EXCLUDE_OBJECT_START '):
                        # Save before the command, so deferred tool selection is
                        # replayed by the guard when this object starts again.
                        self.observe_object(sd)
                    elif outer and script.strip().split(' ', 1)[0].upper() in ('G0', 'G1'):
                        now = self.reactor.monotonic()
                        if self.running and now - getattr(self, 'last_checkpoint_capture', 0.) >= 2.:
                            self.capture_checkpoint(sd.file_position, now, 'interval')
                except Exception:
                    logging.exception('Recovery checkpoint capture failed; print continues')
                before_e = gm.last_position[3] if outer else 0
                result = original(script)
                try:
                    if outer:
                        command = script.strip().split(' ', 1)[0].upper()
                        if command in ('G0', 'G1'):
                            self.retract_debt = max(0., self.retract_debt - (gm.last_position[3] - before_e))
                        elif command in ('START_PRINT', 'CHANGE_TOOL'):
                            state = self.status('gcode_macro TOOL_STATE', self.reactor.monotonic())
                            self.retract_debt = float(state.get('toolchange_retract', 0)) * float(state.get('extrude_factor', 1))
                except Exception:
                    logging.exception('Recovery retraction observation failed')
                return result
            except Exception:
                raise
            finally:
                depth[0] -= 1
        gcode.run_script = observe

    def observe_layer(self, sd):
        now = self.reactor.monotonic()
        if not self.running: self.begin(self.status('print_stats', now), now)
        self.file_layer += 1
        if self.analysis:
            indexed = locate(self.analysis['layers'], sd.file_position)
            if indexed: self.file_layer = indexed['layer']
        if not self.running: return
        self.capture_checkpoint(sd.next_file_position, now, 'layer')

    def observe_object(self, sd):
        if not self.running: return
        self.capture_checkpoint(sd.file_position, self.reactor.monotonic(), 'object')

    def capture_checkpoint(self, offset, now, kind):
        self.last_checkpoint_capture = now
        cp = {'offset': offset, 'layer': self.file_layer, 'kind': kind,
              'snapshot': self.snapshot(now), 'retract_debt': self.retract_debt, 'executed': False}
        session = self.record['session']
        def scheduled(print_time):
            if self.record and self.record['session'] == session:
                cp['print_time'] = print_time
                self.execution_pending.append(cp)
        self.printer.lookup_object('toolhead').register_lookahead_callback(scheduled)

    def status(self, name, now):
        obj = self.printer.lookup_object(name, None)
        started = latency.begin()
        try:
            return obj.get_status(now) if obj else {}
        finally:
            latency.end('status.' + name, started)

    @latency.timed('recovery.snapshot')
    def snapshot(self, now):
        try:
            from .recovery_objects import capture
        except ImportError:
            from recovery_objects import capture
        names = ('print_stats', 'virtual_sdcard', 'toolhead', 'motion_report', 'gcode_move',
                 'extruder', 'heater_bed', 'fan', 'fan_generic chamber_fan',
                 'filament_switch_sensor toolhead_sensor', 'fast_cancel', 'exclude_tool_guard',
                 'exclude_object', 'lugo_tool_temperature', 'screen_mesh',
                 'gcode_macro TOOL_STATE', 'gcode_macro CHANGE_TOOL_STATE',
                 'gcode_macro FIRSTDOCK_STATE', 'gcode_macro PRINT_STATE',
                 'gcode_macro Z_OFFSET_TRACKER')
        result = {name: self.status(name, now) for name in names}
        result['exclusion_internal'] = capture(self.printer)
        gm = self.printer.lookup_object('gcode_move')
        result['gcode_internal'] = {name: copy.deepcopy(getattr(gm, name, None)) for name in
            ('absolute_coord', 'allow_absolute_extrude', 'base_position', 'last_position',
             'homing_position', 'speed', 'speed_factor', 'extrude_factor')}
        mesh = self.printer.lookup_object('bed_mesh', None)
        mesh = mesh.get_mesh() if mesh else None
        if mesh:
            result['active_mesh'] = {'points': mesh.get_probed_matrix(),
                                     'params': dict(mesh.get_mesh_params()),
                                     'offsets': list(mesh.mesh_offsets)}
        ext = self.printer.lookup_object('extruder')
        stepper = ext.extruder_stepper.stepper
        rotation = stepper.get_rotation_distance()[0]
        inverted, original = stepper.get_dir_inverted()
        result['extruder_rotation_distance'] = -rotation if inverted != original else rotation
        result['recorded_at'] = time.time()
        temperatures = self.printer.lookup_object('lugo_tool_temperature', None)
        if temperatures:
            result['temperature_internal'] = {key: copy.deepcopy(getattr(temperatures, key, None)) for key in
                ('active', 'materials', 'base', 'overrides', 'used', 'bed_base', 'bed_override', 'bed_ready')}
        result['monotonic'] = now
        result['position_quality'] = 'observed_not_confirmed_stop'
        started = latency.begin()
        try:
            return json.loads(json.dumps(result, allow_nan=False))
        finally:
            latency.end('recovery.snapshot_json', started)

    @latency.timed('recovery.begin')
    def begin(self, stats, now):
        previous = self.record
        session = uuid.uuid4().hex
        sd = self.printer.lookup_object('virtual_sdcard')
        root = Path(sd.sdcard_dirname).resolve()
        name = stats.get('filename', '')
        source = (root / name).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            return
        if not getattr(self, 'eta_armed', False):
            self.eta_context = None
        self.eta_armed = False
        self.record = {'version': 1, 'session': session, 'boot': self.boot,
                       'filename': name, 'source': str(source), 'started_at': time.time(),
                       'status': 'recording', 'phase': 'recording', 'history': [],
                       'previous_session': previous.get('session') if previous else None}
        try: self.record['system_boot'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        except OSError: pass
        signature = getattr(self, 'config_signature_ready', None)
        if signature is None: signature = self.config_hash()
        self.record['config_signature'] = signature
        gate = self.printer.lookup_object('lugo_preanalysis', None)
        prepared = gate.for_file(source) if gate else None
        self.prepared_analysis = prepared['recovery'] if prepared else None
        self.running = True
        self.last_save = 0.
        self.last_layer = None
        if hasattr(self, 'execution_pending'):
            self.execution_pending.clear()
            self.file_layer = 0
            self.analysis = None
            self.resume_token = None

    @latency.timed('recovery.tick')
    def tick(self, now):
        # print_stats may still say printing after an MCU shutdown. Never
        # interpret that stale state as a new job or replace the saved checkpoint.
        if self.printer.is_shutdown():
            return now + 1.
        try:
            dirty = False
            if self.record and self.running and not getattr(self, 'recovering', False):
                dirty = self.observe_position(now, persist=False)
            if hasattr(self, 'execution_pending') and self.record and self.running:
                estimated = self.status('toolhead', now).get('estimated_print_time', -1)
                changed = False
                while self.execution_pending and self.execution_pending[0]['print_time'] + .1 <= estimated:
                    cp = self.execution_pending.popleft()
                    cp['executed'] = True
                    if not validate_checkpoint(cp):
                        self.record['checkpoint'] = cp
                    changed = True
                if changed: dirty = True
            stats = self.status('print_stats', now)
            state = stats.get('state')
            if state in ('printing', 'paused'):
                if not self.running:
                    self.begin(stats, now)
                if self.running:
                    layer = stats.get('info', {}).get('current_layer')
                    if now - self.last_save >= 5 or layer != self.last_layer:
                        snap = self.snapshot(now)
                        self.record['snapshot'] = snap
                        history = self.record['history']
                        history.append({'time': snap['recorded_at'], 'layer': layer,
                            'file_position': snap['virtual_sdcard'].get('file_position'),
                            'live_position': snap['motion_report'].get('live_position'),
                            'gcode_position': snap['gcode_move'].get('gcode_position'),
                            'tool': snap['gcode_macro TOOL_STATE'].get('active_tool'),
                            'docking': snap['fast_cancel'].get('phase')})
                        del history[:-120]
                        self.last_save, self.last_layer = now, layer
                        dirty = True
            elif self.running and state in ('complete', 'cancelled', 'error'):
                self.record['status'] = {'complete': 'completed', 'cancelled': 'cancelled',
                                         'error': 'interrupted'}[state]
                self.record['reason'] = stats.get('message', '')
                self.record['ended_at'] = time.time()
                self.running = False
                dirty = True
            if dirty: self.submit()
        except Exception:
            logging.exception('Recovery journal observation failed')
        return now + (.25 if self.running or self.recovering else 1.)

    def observe_position(self, now, persist=True):
        th = self.status('toolhead', now)
        live = self.status('motion_report', now).get('live_position') or []
        if 'z' not in th.get('homed_axes', '') or len(live) < 3:
            return
        z = live[2]
        if not isinstance(z, (int, float)) or not math.isfinite(z):
            return
        self.record['stop_position'] = {
            'z': z, 'recorded_at': time.time(), 'monotonic': now,
            'source': 'motion_report_live_position', 'sample_interval': .25,
            'save_interval': 1., 'quality': 'estimated_not_confirmed_stop'}
        # Disk work remains on the existing bounded background writer. A
        # shutdown flush includes the latest in-memory quarter-second sample.
        if now - getattr(self, 'last_pose_save', 0.) >= 1.:
            self.last_pose_save = now
            if persist: self.submit()
            return True
        return False

    def shutdown(self):
        if self.record and self.record.get('boot') == self.boot:
            # note_error may have already set running=False with only "MCU
            # shutdown". Preserve the detailed printer error independently.
            self.record['shutdown_detail'] = str(self.printer.get_state_message()[0])
            self.submit()
        if self.running and self.record:
            self.record['status'] = 'interrupted'
            self.record['reason'] = str(self.printer.get_state_message()[0])
            self.record['ended_at'] = time.time()
            # Keep last pre-shutdown snapshot, never mistake shutdown coordinates for confirmed position.
            self.running = False
            self.submit()

    @latency.timed('recovery.submit')
    def submit(self):
        if not self.record: return
        now = self.reactor.monotonic()
        # Coalesce checkpoints and position updates into at most one queued
        # periodic save per second. Terminal/error transitions are immediate.
        if self.record.get('status') == 'recording':
            if now - getattr(self, 'last_submit', 0.) < 1.: return
            self.last_submit = now
        started = latency.begin()
        try:
            item = copy.deepcopy(self.record)
        finally:
            latency.end('recovery.submit_copy', started)
        item['_prepared_analysis'] = getattr(self, 'prepared_analysis', None)
        try:
            self.pending.put_nowait(item)
        except queue.Full:
            try:
                self.pending.get_nowait()
            except queue.Empty:
                pass
            self.pending.put_nowait(item)

    @latency.timed('recovery.analyze_worker')
    def analyze_worker(self, source):
        # Called only by the existing writer, never by the Reactor. A Python
        # thread still competes for the Klipper interpreter GIL; isolate parsing.
        worker = Path(__file__).with_name('recovery_worker.py')
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            result = subprocess.run([sys.executable, '-I', str(worker), str(source)],
                                    stdout=output, stderr=errors, timeout=600,
                                    check=False, close_fds=True)
            if result.returncode:
                errors.seek(0)
                raise RuntimeError('Recovery index worker failed: ' + errors.read(2048).decode('utf-8', 'replace'))
            if output.tell() > 32 * 1024 * 1024:
                raise ValueError('Recovery index result exceeds limit')
            output.seek(0)
            return json.load(output)

    def write_loop(self):
        identified = {}
        while True:
            data = self.pending.get()
            try:
                session = data['session']
                prepared = data.pop('_prepared_analysis', None)
                if session not in identified:
                    source = Path(data['source'])
                    analysis = prepared if prepared is not None else self.analyze_worker(source)
                    if data.get('identity') and data['identity']['sha256'] != analysis['identity']['sha256']:
                        raise ValueError('Original print file has changed')
                    identified.clear()
                    identified[session] = analysis['identity']
                    def publish(eventtime, session=session, analysis=analysis):
                        if self.record and self.record['session'] == session:
                            self.analysis = analysis
                            self.record['identity'] = analysis['identity']
                    self.reactor.register_async_callback(publish)
                data['identity'] = identified[session]
                self.persist_record(data)
                self.write_error = ''
            except Exception as exc:
                self.write_error = str(exc)
                logging.exception('Recovery journal disk write failed')

    def persist_record(self, data):
        session = data['session']
        # Discard and writes share a lock so an already queued/in-flight save
        # cannot recreate a deleted recovery candidate.
        with self.io_lock:
            if session in self.deleted_sessions:
                return
            fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).digest()
            if self.last_written == (session, fingerprint):
                return
            previous = read_record(self.path) if self.last_written is None or self.last_written[0] != session else None
            if previous and previous['session'] != session and previous['session'] not in self.deleted_sessions:
                atomic_json(self.folder / (previous['session'] + '.json'), previous)
            data = dict(data, saved_at=time.time())
            # Only one full periodic write. Archive a terminal state once;
            # subsequent state changes or a new print preserve it separately.
            atomic_json(self.path, data)
            archive_key = (session, data.get('status'), data.get('phase'))
            if data.get('status') != 'recording' and archive_key not in self.archived_states:
                atomic_json(self.folder / (session + '.json'), data)
                self.archived_states.add(archive_key)
            self.last_written = (session, fingerprint)
            # Keep at most two older session records; newest first. The active
            # current.json is separate. Never touch G-code/config/log files.
            archives = sorted((p for p in self.folder.glob('*.json')
                if len(p.stem) == 32 and all(c in '0123456789abcdef' for c in p.stem)),
                key=lambda p:p.stat().st_mtime, reverse=True)
            for old in archives[2:]: old.unlink(missing_ok=True)

    def discard_record(self):
        session = self.record['session']
        # Session names come from the journal, never allow path traversal.
        if not session or any(c not in '0123456789abcdef' for c in session):
            raise ValueError('Invalid recovery session')
        with self.io_lock:
            self.deleted_sessions.add(session)
            current = read_record(self.path)
            if current and current.get('session') == session:
                self.path.unlink(missing_ok=True)
            (self.folder / (session + '.json')).unlink(missing_ok=True)
            # Remove interrupted atomic-write remnants for this session only.
            (self.folder / (session + '.tmp')).unlink(missing_ok=True)
            if not self.path.exists():
                self.path.with_suffix('.tmp').unlink(missing_ok=True)
            if os.name != 'nt':
                fd = os.open(str(self.folder), os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
        self.record = None
        self.analysis = None
        self.resume_token = None

    def cleanup_missing_sources(self, now):
        # Idle-only metadata checks: never scan G-code contents or interfere
        # with a running print. Two misses avoid transient rename/upload gaps.
        try:
            if (self.running or self.recovering or
                    self.status('print_stats', now).get('state') in ('printing', 'paused')):
                return now + 5.
            root = Path(self.printer.lookup_object('virtual_sdcard').sdcard_dirname).resolve()
            if not root.is_dir(): return now + 5.
            records = [self.record] if self.record else []
            for p in self.folder.glob('*.json'):
                if len(p.stem) == 32 and all(c in '0123456789abcdef' for c in p.stem):
                    data = read_record(p)
                    if data: records.append(data)
            missing = set()
            for data in records:
                name = data.get('filename', '')
                if not name: continue
                source = (root / name).resolve()
                if not source.is_relative_to(root): continue
                try:
                    source.stat()
                    continue
                except FileNotFoundError:
                    missing.add(name)
                except OSError:
                    continue  # Permission/I/O errors are not deletion.
            self.missing_sources = {n:self.missing_sources.get(n, 0)+1 for n in missing}
            for data in records:
                if self.missing_sources.get(data.get('filename'), 0) < 2: continue
                session = data['session']
                if len(session) != 32 or any(c not in '0123456789abcdef' for c in session): continue
                if self.record and self.record['session'] == session:
                    self.discard_record()
                else:
                    with self.io_lock:
                        self.deleted_sessions.add(session)
                        (self.folder / (session + '.json')).unlink(missing_ok=True)
                        (self.folder / (session + '.tmp')).unlink(missing_ok=True)
        except Exception:
            logging.exception('Recovery source cleanup failed')
        return now + 5.

    def get_status(self, eventtime):
        return {'recording': self.running, 'available': candidate(self.record, self.boot),
                'session': self.record.get('session') if self.record else None,
                'write_error': self.write_error, 'phase': 'review_required',
                'recovering': getattr(self, 'recovering', False),
                'stage': getattr(self, 'recovery_stage', ''),
                'error': getattr(self, 'recovery_error', ''),
                'eta': self.get_recovery_eta()}

    def get_recovery_eta(self):
        context = getattr(self, 'eta_context', None)
        if not context: return None
        now = self.reactor.monotonic()
        return estimate(context, self.status('print_stats', now),
                        self.status('virtual_sdcard', now).get('file_position', 0))

    def start_recovery_eta(self, filename, offset):
        timeline = (self.analysis or {}).get('timeline', [])
        self.eta_context = {'filename':filename, 'offset':offset, 'timeline':timeline,
                            'initial_remaining':remaining_at(timeline, offset)}
        self.eta_armed = True

    def control(self, request):
        action = request.get_str('action', 'status')
        if action == 'abort':
            if getattr(self, 'recovering', False):
                self.abort_requested = True
                self.printer.lookup_object('heaters').turn_off_all_heaters()
            request.send({'aborted': True})
            return
        if action == 'status':
            request.send({'state': self.get_status(0), 'record': self.record or {},
                          'proposal': self.proposal()})
            return
        if self.running or getattr(self, 'recovering', False) or self.status('print_stats', self.reactor.monotonic()).get('state') in ('printing', 'paused'):
            raise request.error('Recovery review requires an idle printer')
        if not candidate(self.record, self.boot):
            raise request.error('No interrupted print record')
        if request.get_str('session') != self.record['session']:
            raise request.error('Recovery record changed; reopen the review')
        if action == 'prepare':
            self.prepare_resume(request)
            return
        if action == 'discard':
            try:
                self.discard_record()
            except (OSError, ValueError) as exc:
                raise request.error(str(exc))
            request.send({'state': self.get_status(0), 'record': {}})
            return
        elif action == 'review':
            tool = request.get_int('tool')
            unchanged = request.get_int('z_unchanged')
            layer = request.get_int('completed_layer', 0)
            if tool not in (-1, 0, 1, 2, 3) or unchanged not in (0, 1) or not 0 <= layer <= 100000:
                raise request.error('Invalid recovery selection')
            detected = self.status('filament_switch_sensor toolhead_sensor', self.reactor.monotonic()).get('filament_detected')
            if detected is None or bool(detected) != (tool >= 0):
                raise request.error('Selected tool does not match the toolhead detection sensor')
            if not unchanged:
                raise request.error('Z position must be checked before recovery')
            self.record['review'] = {'tool': tool, 'z_unchanged': True, 'completed_layer': layer,
                                      'at': time.time(), 'motion_enabled': False}
        else:
            raise request.error('Unknown recovery action')
        self.submit()
        request.send({'state': self.get_status(0), 'record': self.record})


def load_config(config):
    return Recovery(config)
