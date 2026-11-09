"""LUGOWARE supervised recovery. Never runs on startup or a status request.

Only execution-timed checkpoints are executable. Last observed machine Z is a
best-effort estimate, never an exact power-loss position. Manual parking and
unchanged bed height must be confirmed before this supervised trial.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid
try:
    from .recovery_index import locate, validate_checkpoint
except ImportError:
    from recovery_index import locate, validate_checkpoint


class RecoveryExecution:
    def resume_point(self):
        cp = (self.record or {}).get('checkpoint')
        analysis = getattr(self, 'analysis', None)
        if not cp or not analysis:
            return None
        point = locate(analysis['layers'], cp['offset'])
        if point is not None:
            point['execution_offset'] = cp['offset']
        return point

    def estimated_stop(self):
        record = self.record or {}
        pose = record.get('stop_position')
        if pose is None:
            # Compatibility with existing 5-second records: use live machine
            # position, NEVER the G-code layer height or queued toolhead target.
            snap = record.get('snapshot', {})
            live = snap.get('motion_report', {}).get('live_position') or []
            if len(live) < 3 or 'z' not in snap.get('toolhead', {}).get('homed_axes', ''):
                return None
            pose = {'z': live[2], 'recorded_at': snap.get('recorded_at'),
                    'source': 'legacy_live_position', 'save_interval': 5.}
        if (not isinstance(pose, dict) or not isinstance(pose.get('z'), (float, int))
                or not math.isfinite(pose['z'])):
            return None
        result = dict(pose)
        ended = record.get('ended_at')
        if ended is not None and pose.get('recorded_at') is not None:
            result['age_at_interrupt'] = max(0., ended - pose['recorded_at'])
        return result

    def check_recovery_abort(self):
        cancel = self.printer.lookup_object('fast_cancel', None)
        if self.abort_requested or self.printer.is_shutdown() or (cancel and cancel.requested):
            raise self.printer.lookup_object('gcode').error('Recovery preparation cancelled')

    def proposal(self):
        record = self.record or {}
        cp = record.get('checkpoint')
        analysis = getattr(self, 'analysis', None)
        position = record.get('snapshot', {}).get('virtual_sdcard', {}).get('file_position', 0)
        observed = locate(analysis['layers'], position) if analysis else None
        point = self.resume_point()
        reason = validate_checkpoint(cp)
        if not reason and not analysis:
            reason = 'Checking original print file…'
        if not reason and point is None:
            reason = 'No matching restart layer in the original file.'
        stop = self.estimated_stop()
        if not reason and stop is None:
            reason = 'No usable observed machine position is saved.'
        return {'observed': observed, 'resume': point, 'reason': reason,
                'can_prepare': not reason, 'legacy': not bool(cp),
                'estimated_stop': stop,
                'total_layers': len(analysis['layers']) if analysis else None}

    def config_hash(self):
        settings = self.status('configfile', self.reactor.monotonic()).get('settings', {})
        return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()

    def validate_resume(self, tool, physical_z):
        if self.printer.is_shutdown(): raise ValueError('Printer is shutdown')
        reason = self.proposal()['reason']
        if reason: raise ValueError(reason)
        if self.record.get('config_signature') != self.config_hash():
            raise ValueError('Printer configuration changed since this print.')
        sd = self.printer.lookup_object('virtual_sdcard')
        path = (Path(sd.sdcard_dirname) / self.record['filename']).resolve()
        if not path.is_relative_to(Path(sd.sdcard_dirname).resolve()):
            raise ValueError('Invalid original file path')
        stat = path.stat()
        identity = self.analysis['identity']
        if (stat.st_size, stat.st_mtime_ns) != (identity['size'], identity['mtime_ns']):
            raise ValueError('Original print file has changed')
        cp = self.record['checkpoint']
        if not 0 < cp['offset'] < stat.st_size: raise ValueError('Invalid checkpoint file position')
        self.make_mesh(cp['snapshot']['active_mesh'])  # validate before any movement or heating
        if tool != -1 or self.status('filament_switch_sensor toolhead_sensor', 0).get('filament_detected') is not False:
            raise ValueError('Park/remove the mounted head manually before recovery. No tool must be detected.')
        th = self.status('toolhead', self.reactor.monotonic())
        minimum, maximum = th['axis_minimum'][2], th['axis_maximum'][2]
        target = self.record['checkpoint']['snapshot']['toolhead']['position'][2]
        if not math.isfinite(physical_z) or not minimum <= physical_z <= maximum - 5:
            raise ValueError('Current physical Z is outside the safe recovery range.')
        clearance = max(physical_z, target) + 5
        if clearance > maximum: raise ValueError('Insufficient Z clearance for recovery.')
        settings = self.status('configfile', 0).get('settings', {})
        if settings.get('homing_override', {}).get('axes', '').lower() != 'z':
            raise ValueError('XY-only homing configuration is required.')
        self.station_approach()  # Validate model-specific path before any movement.
        return clearance

    def station_approach(self):
        settings = self.status('configfile', self.reactor.monotonic()).get('settings', {})
        source = settings.get('gcode_macro start_print', {}).get('gcode', '')
        commands = [line.split('#', 1)[0].strip() for line in source.splitlines()]
        lines = [line for line in commands if line.upper().startswith('EXCLUDE_TOOL_PREPARE ')]
        if len(lines) != 1:
            raise ValueError('Cannot determine the configured tool station approach.')
        values = {}
        for key in ('APPROACH_X', 'APPROACH_F'):
            match = re.search(r'(?:^|\s)' + key + r'=([-+]?\d+(?:\.\d+)?)(?=\s|$)', lines[0], re.I)
            if not match:
                raise ValueError('Tool station approach must use explicit numeric coordinates and speed.')
            values[key] = float(match.group(1))
        th = self.status('toolhead', self.reactor.monotonic())
        if not th['axis_minimum'][0] <= values['APPROACH_X'] <= th['axis_maximum'][0]:
            raise ValueError('Tool station approach is outside the configured X range.')
        speed = float(settings.get('printer', {}).get('max_velocity', 0))
        if speed <= 0 or values['APPROACH_F'] <= 0:
            raise ValueError('Invalid recovery movement speed configuration.')
        return values['APPROACH_X'], min(values['APPROACH_F'], speed * 60.)

    def make_mesh(self, saved):
        from .bed_mesh import ZMesh
        mesh = ZMesh(dict(saved['params']), 'recovery')
        mesh.build_mesh(saved['points'])
        mesh.set_mesh_offsets(saved.get('offsets', [0., 0.]))
        return mesh

    def prepare_resume(self, request):
        try:
            tool = -1
            stop = self.estimated_stop()
            if stop is None:
                raise ValueError('No usable observed machine position is saved.')
            physical_z = stop['z']
            if request.get_int('checks', 0) != 1:
                raise ValueError('Confirm unchanged bed height, parked head and clear paths.')
            clearance = self.validate_resume(tool, physical_z)
            self.resume_token = {'token': uuid.uuid4().hex, 'session': self.record['session'],
                                 'physical_z': physical_z, 'tool': tool, 'clearance': clearance,
                                 'expires': self.reactor.monotonic() + 120}
            request.send({'token': self.resume_token['token'], 'proposal': self.proposal(),
                          'clearance': clearance})
        except (ValueError, OSError, KeyError) as exc:
            raise request.error(str(exc))

    def resume_command(self, gcmd):
        token = self.resume_token
        self.resume_token = None  # one-shot, including failed attempts
        if (not token or gcmd.get('TOKEN', '') != token['token']
                or token['session'] != self.record['session']
                or self.reactor.monotonic() > token['expires']):
            raise gcmd.error('Recovery approval expired; review again.')
        if self.running or self.recovering or self.status('print_stats', 0).get('state') in ('printing', 'paused'):
            raise gcmd.error('Recovery requires an idle printer')
        try:
            self.validate_resume(token['tool'], token['physical_z'])
        except (ValueError, OSError, KeyError) as exc:
            raise gcmd.error(str(exc))
        cp = copy.deepcopy(self.record['checkpoint'])
        # Retain confirmed exclusions requested after the chosen layer checkpoint.
        latest = self.record.get('snapshot', {}).get('exclude_object', {})
        saved = cp['snapshot'].setdefault('exclude_object', {})
        saved['excluded_objects'] = sorted(set(saved.get('excluded_objects', [])) |
                                           set(latest.get('excluded_objects', [])))
        restart = self.resume_point()
        record = copy.deepcopy(self.record)
        self.recovering = True
        self.abort_requested = False
        self.record['phase'] = 'preparing_recovery'
        self.recovery_stage = 'homing'
        self.recovery_error = ''
        self.submit()
        gcode = self.printer.lookup_object('gcode')
        def run(command):
            self.check_recovery_abort()
            gcode.run_script_from_command(command)
            self.check_recovery_abort()
        try:
            self.execute_setup(cp, token, run)
            sd = self.printer.lookup_object('virtual_sdcard')
            stat = (Path(sd.sdcard_dirname) / record['filename']).stat()
            identity = self.analysis['identity']
            if (stat.st_size, stat.st_mtime_ns) != (identity['size'], identity['mtime_ns']):
                raise ValueError('Original print file has changed')
            sd._reset_file()
            sd._load_file(gcmd, record['filename'], check_subdirs=True)
            sd.file_position = restart['execution_offset']
            self.restore_objects(cp['snapshot'], run)
            self.record['phase'] = 'resumed'
            self.submit()
            self.running = False
            self.file_layer = restart['layer'] - 1
            self.recovering = False
            self.start_recovery_eta(record['filename'], restart['execution_offset'])
            sd.do_resume()
            # Retire the consumed candidate immediately. A resumed job starts
            # its own journal, so a second interruption remains recoverable.
            self.discard_record()
            self.begin(self.status('print_stats', self.reactor.monotonic()), self.reactor.monotonic())
            run('M117 PRINTING...')
        except Exception as exc:
            if self.record is None: self.record = record
            self.record['status'] = 'interrupted'
            self.record['phase'] = 'recovery_failed'
            self.recovery_stage = 'failed'
            self.recovery_error = str(exc)
            self.submit()
            # Do not issue any emergency parking movement after a failed setup.
            self.printer.lookup_object('heaters').turn_off_all_heaters()
            raise gcmd.error(str(exc))
        finally:
            self.recovering = False

    def execute_setup(self, cp, approval, run):
        snap = cp['snapshot']
        st = snap['gcode_macro TOOL_STATE']
        tool = int(st['active_tool'])
        temperature = float(snap['extruder']['target'])
        bed = float(snap['heater_bed']['target'])
        run('BED_MESH_CLEAR\nG21\nG90\nM83\nM220 S100\nM221 S100\nSET_GCODE_OFFSET X=0 Y=0 Z=0 MOVE=0')
        run('SET_EXTRUDER_ROTATION_DISTANCE EXTRUDER=extruder DISTANCE=%.8f' % snap['extruder_rotation_distance'])
        run('SET_KINEMATIC_POSITION Z=%.6f SET_HOMED=Z CLEAR_HOMED=XY' % approval['physical_z'])
        run('G92 Z%.6f\nG1 Z%.6f F600\nG28 X\nG28 Y' % (approval['physical_z'], approval['clearance']))
        # Preserve the material/diameter/prime configuration for this actual tool.
        for key, value in st.items():
            if key in self.printer.lookup_object('gcode_macro TOOL_STATE').variables:
                self.printer.lookup_object('gcode_macro TOOL_STATE').variables[key] = copy.deepcopy(value)
        self.printer.lookup_object('gcode_macro TOOL_STATE').variables['active_tool'] = -1
        run('SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=0\nPRINT_SENSOR_GATE ENABLE=0')
        self.recovery_stage = 'heating'
        run('M140 S%.3f\nM104 S%.3f' % (bed, temperature))
        if bed > 0: run('TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM=%.3f' % max(0, bed - 2))
        # Match START_PRINT station approach (F9000).
        run('G1 X%.6f F%.6f' % self.station_approach())
        params = ' '.join('%s=%.6f' % (p, float(st.get(k, default))) for p, k, default in (
            ('FOAM', 'prime_foam', 0), ('MVS', 'prime_mvs', 0), ('P1', 'prime_p1', 6),
            ('P2', 'prime_p2', 3), ('FP0', 'prime_fp0', 18), ('FP1', 'prime_fp1', 6),
            ('FP2', 'prime_fp2', 3), ('H_D', 'prime_h_d', 0)))
        self.recovery_stage = 'docking'
        run('DOCK_TOOL_%d EXTRUDER_TEMP=%.3f FIRST_USE=0 %s' % (tool, temperature, params))
        # Docking primes above the print target. Do not wait for cooling at
        # the station exit; retain the lower-temperature extrusion guard.
        run('M104 S%.3f\nTEMPERATURE_WAIT SENSOR=extruder MINIMUM=%.3f' %
            (temperature, temperature - 2))
        self.recovery_stage = 'returning'
        run('M400')
        if self.status('filament_switch_sensor toolhead_sensor', 0).get('filament_detected') is not True:
            raise ValueError('Tool attachment was not confirmed after docking.')
        # Match the checkpoint retraction, rather than adding an arbitrary prime on the model.
        amount = float(st.get('toolchange_retract', 0)) * float(st.get('extrude_factor', 1)) - float(cp.get('retract_debt', 0))
        if abs(amount) > 0.000001: run('M83\nG1 E%.6f F600' % amount)
        run('M400')
        mesh = self.make_mesh(snap['active_mesh'])
        self.printer.lookup_object('bed_mesh').set_mesh(mesh)
        gm = self.printer.lookup_object('gcode_move')
        state = copy.deepcopy(snap['gcode_internal'])
        # Return XY at clearance first, then Z; NEVER restore with a diagonal descent.
        th = self.printer.lookup_object('toolhead')
        destination = snap['toolhead']['position']
        # Match RESUME's F60000 XY return. Keep sequential XY then Z;
        settings = self.status('configfile', self.reactor.monotonic())['settings']['printer']
        xy_speed = min(1000., float(settings['max_velocity']))
        z_speed = min(40., float(settings.get('max_z_velocity', xy_speed)))
        th.manual_move([destination[0], destination[1], None], xy_speed)
        th.manual_move([None, None, destination[2]], z_speed)
        th.wait_moves()
        gm.saved_states['_LUGO_RECOVERY'] = state
        run('RESTORE_GCODE_STATE NAME=_LUGO_RECOVERY MOVE=0')
        for name in ('TOOL_STATE', 'FIRSTDOCK_STATE', 'Z_OFFSET_TRACKER', 'CHANGE_TOOL_STATE', 'PRINT_STATE'):
            macro = self.printer.lookup_object('gcode_macro ' + name, None)
            if macro is None: continue
            for key, value in snap.get('gcode_macro ' + name, {}).items():
                if key in macro.variables: macro.variables[key] = copy.deepcopy(value)
        ext = snap['extruder']
        if 'pressure_advance' in ext:
            run('SET_PRESSURE_ADVANCE ADVANCE=%.6f SMOOTH_TIME=%.6f' %
                (ext['pressure_advance'], ext.get('smooth_time', .04)))
        limits = snap['toolhead']
        run('SET_VELOCITY_LIMIT VELOCITY=%.6f ACCEL=%.6f SQUARE_CORNER_VELOCITY=%.6f MINIMUM_CRUISE_RATIO=%.6f' %
            tuple(limits[k] for k in ('max_velocity', 'max_accel', 'square_corner_velocity', 'minimum_cruise_ratio')))
        run('M106 S%.6f' % (255 * snap.get('fan', {}).get('speed', 0)))
        run('SET_FAN_SPEED FAN=chamber_fan SPEED=%.6f' % snap.get('fan_generic chamber_fan', {}).get('speed', 0))
        run('FAST_CANCEL_PHASE PHASE=docked TOOL=%d\nPRINT_SENSOR_GATE ENABLE=0' % tool)
        temperatures = self.printer.lookup_object('lugo_tool_temperature', None)
        if temperatures and snap.get('temperature_internal'):
            temperatures.reset()
            for key, value in snap['temperature_internal'].items():
                setattr(temperatures, key, copy.deepcopy(value))
            temperatures.start_tool = None

    def restore_objects(self, snap, run):
        for obj in snap.get('exclude_object', {}).get('objects', []):
            name = obj['name']
            if not re.fullmatch(r'[\w.:-]+', name): raise ValueError('Unsupported object name')
            args = ' '.join('%s=%s' % (key.upper(), (','.join(str(v) for v in obj[key]) if key == 'center' else json.dumps(obj[key], separators=(',', ':'))))
                            for key in ('center', 'polygon') if key in obj)
            run('EXCLUDE_OBJECT_DEFINE NAME=%s %s' % (name, args))
        for name in snap.get('exclude_object', {}).get('excluded_objects', []):
            if not re.fullmatch(r'[\w.:-]+', name): raise ValueError('Unsupported object name')
            run('EXCLUDE_OBJECT NAME=%s' % name)
        current = snap.get('exclude_object', {}).get('current_object')
        if current:
            if not re.fullmatch(r'[\w.:-]+', current): raise ValueError('Unsupported object name')
            run('EXCLUDE_OBJECT_START NAME=%s' % current)
        try:
            from .recovery_objects import restore
        except ImportError:
            from recovery_objects import restore
        restore(self.printer, snap)
        if (snap.get('exclude_object', {}).get('excluded_objects')
                and not snap.get('exclusion_internal', {}).get('transform')):
            # New exclusion after checkpoint: do not print five warm-up moves
            # inside an already excluded part after restoration.
            self.printer.lookup_object('exclude_object').initial_extrusion_moves = 0
        # SD reset/transform installation can reset the G-code position cache.
        gm = self.printer.lookup_object('gcode_move')
        gm.saved_states['_LUGO_RECOVERY'] = copy.deepcopy(snap['gcode_internal'])
        run('RESTORE_GCODE_STATE NAME=_LUGO_RECOVERY MOVE=0')
