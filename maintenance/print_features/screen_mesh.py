"""Per-job mesh selection and restart-free persistent mesh for the .151 trial."""
import json
import logging
import math
import os
import tempfile
import time
from .bed_mesh import ZMesh


class ScreenMesh:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.path = os.path.expanduser(config.get('path'))
        self.pending = True
        self.last_action = ''
        self.gcode.register_command('SCREEN_MESH_SELECT', self.select)
        self.gcode.register_command('SCREEN_MESH_PREPARE', self.prepare)
        self.gcode.register_command('SCREEN_MESH_STORE', self.store_command)
        self.gcode.register_command('SCREEN_MESH_AUDIT', lambda gcmd: self.audit('after_docking'))

    def get_status(self, eventtime):
        return {'enabled': self.pending, 'last_action': self.last_action,
                'stored': os.path.isfile(self.path)}

    def select(self, gcmd):
        self.pending = bool(gcmd.get_int('ENABLE', 1, minval=0, maxval=1))

    def signature(self):
        settings = self.printer.lookup_object('configfile').get_status(0)['settings']
        return {name: settings.get(name, {}) for name in
                ('probe', 'axis_twist_compensation', 'bed_mesh', 'stepper_z')}

    def write_mesh(self):
        mesh = self.printer.lookup_object('bed_mesh').get_mesh()
        if mesh is None:
            raise ValueError('No active mesh to save')
        data = {'version': 1, 'saved_at': time.time(),
                'signature': self.signature(),
                'points': mesh.get_probed_matrix(),
                'mesh_params': dict(mesh.get_mesh_params())}
        encoded = json.dumps(data, allow_nan=False).encode('utf-8')
        folder = os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.mesh-', dir=folder)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def restore(self):
        with open(self.path, encoding='utf-8') as stream:
            data = json.load(stream)
        # Normalize tuples from runtime settings to JSON lists.
        signature = json.loads(json.dumps(self.signature()))
        saved_signature = data.get('signature', {})
        # Tension changes interpolation only, not the measured bed coordinates.
        saved_signature = json.loads(json.dumps(saved_signature))
        for item in (saved_signature, signature):
            for key in ('bicubic_tension', 'move_check_distance', 'split_delta_z'):
                item.get('bed_mesh', {}).pop(key, None)
        if data.get('version') != 1 or saved_signature != signature:
            raise ValueError('Saved mesh does not match current configuration')
        params, points = dict(data['mesh_params']), data['points']
        settings = self.signature().get('bed_mesh', {})
        params['tension'] = float(settings.get('bicubic_tension', .2))
        if len(points) != params['y_count'] or any(
                len(row) != params['x_count'] for row in points):
            raise ValueError('Invalid saved mesh dimensions')
        if not all(math.isfinite(float(v)) for row in points for v in row):
            raise ValueError('Invalid saved mesh values')
        mesh = ZMesh(params, 'screen_last')
        mesh.build_mesh(points)
        self.printer.lookup_object('bed_mesh').set_mesh(mesh)

    def audit(self, phase):
        now = self.printer.get_reactor().monotonic()
        mesh = self.printer.lookup_object('bed_mesh').get_mesh()
        points = mesh.get_probed_matrix() if mesh else None
        move = self.printer.lookup_object('gcode_move').get_status(now)
        bed = self.printer.lookup_object('heater_bed').get_status(now)
        logging.info('Screen mesh audit: %s', json.dumps({
            'phase': phase, 'action': self.last_action,
            'points': points,
            'params': dict(mesh.get_mesh_params()) if mesh else None,
            'bed_temp': bed['temperature'], 'bed_target': bed['target'],
            'origin': list(move['homing_origin']),
            'gcode_position': list(move['gcode_position']),
            'toolhead_position': list(self.printer.lookup_object('toolhead').get_position()),
        }))

    def store_command(self, gcmd):
        try:
            self.write_mesh()
        except Exception as exc:
            logging.exception('Mesh save failed')
            raise gcmd.error('Mesh save failed.')
        gcmd.respond_info('Latest mesh saved without restart.')

    def cancelled(self):
        cancel = self.printer.lookup_object('fast_cancel', None)
        if self.printer.is_shutdown() or (cancel is not None and cancel.requested):
            self.last_action = 'cancelled'
            logging.info('Screen mesh: cancellation detected; save and heating skipped')
            return True
        return False

    def prepare(self, gcmd):
        enabled = self.pending
        self.pending = True  # Consume selection once; other print paths default ON.
        if self.cancelled():
            return
        if not enabled:
            try:
                self.restore()
            except Exception as exc:
                logging.warning('Saved mesh unavailable: %s', exc)
                raise gcmd.error('Saved mesh unavailable. Enable bed mesh and retry.')
            else:
                self.last_action = 'loaded'
                logging.info('Screen mesh: loaded saved mesh for print')
                self.audit('prepared')
                self.gcode.run_script_from_command('M117 Heating...')
                gcmd.respond_info('Latest saved bed mesh loaded.')
                return
        self.gcode.run_script_from_command('M117 Bed Mesh...')
        bedmesh = self.printer.lookup_object('bed_mesh')
        bedmesh.set_mesh(None)
        # Errors propagate: never save a partial or stale measurement.
        self.gcode.run_script_from_command('BED_MESH_CALIBRATE')
        # FastCancel intentionally returns normally after safe probe cleanup.
        # Do not mistake that return for a completed calibration.
        if self.cancelled():
            return
        try:
            self.write_mesh()
        except Exception as exc:
            logging.exception('Mesh save failed')
            raise gcmd.error('Mesh save failed.')
        self.last_action = 'measured_saved'
        logging.info('Screen mesh: measured and saved mesh for print')
        self.audit('prepared')
        gcmd.respond_info('Latest mesh saved without restart.')
        self.gcode.run_script_from_command('M117 Heating...')


def load_config(config):
    return ScreenMesh(config)
