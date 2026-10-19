"""Retry a whole mesh point, without adding waits to successful probing."""
import logging
import math

ERROR = 'Probe triggered prior to movement'

class ProbeAutoRecovery:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.attempts = config.getint('attempts', 2, minval=1, maxval=2)
        self.minimum_clearance = config.getfloat('minimum_clearance', 1., above=0.)
        self.recoveries = self.reactivations = 0
        self.printer.register_event_handler('klippy:ready', self.ready)

    def ready(self):
        probe = self.printer.lookup_object('probe')
        self.wrapper = probe.mcu_probe
        self.session = probe.probe_session
        self.offset = probe.get_offsets()[2]
        self.toolhead = self.printer.lookup_object('toolhead')
        self.fast_cancel = self.printer.lookup_object('fast_cancel')
        self.original = self.session.run_probe
        self.session.run_probe = self.run_probe

    def get_status(self, eventtime):
        return {'recoveries': self.recoveries, 'reactivations': self.reactivations,
                'attempts': self.attempts, 'scope': 'bed_mesh_whole_point',
                'normal_path_extra_wait': False, 'preserve_higher_z': True, 'recovery_lift': 2.0}

    def safe(self, gcmd, start):
        fc = self.fast_cancel
        if self.printer.is_shutdown() or fc.requested or fc.cleaning or fc.homing_active:
            return False
        status = self.toolhead.get_status(self.printer.get_reactor().monotonic())
        if set('xyz') - set(status['homed_axes']):
            return False
        current = self.toolhead.get_position()
        if not all(math.isfinite(v) for v in current[:3] + start[:3]):
            return False
        if any(abs(current[i] - start[i]) > .001 for i in (0, 1)):
            return False
        config = self.printer.lookup_object('configfile').get_status(
            self.printer.get_reactor().monotonic())['settings']['bed_mesh']
        clearance = gcmd.get_float('HORIZONTAL_MOVE_Z', config['horizontal_move_z'])
        return (start[2] >= max(clearance, self.offset + self.minimum_clearance) - .001
                and status['axis_minimum'][2] <= current[2] <= status['axis_maximum'][2]
                and start[2] <= status['axis_maximum'][2])

    def triggered(self):
        self.toolhead.wait_moves()
        return bool(self.wrapper.query_endstop(self.toolhead.get_last_move_time()))

    def recover(self, gcmd, start):
        if not self.safe(gcmd, start):
            raise self.printer.command_error(ERROR)
        self.wrapper._raise_probe()
        # Only retract away from the bed at the unchanged XY coordinates.
        status = self.toolhead.get_status(self.printer.get_reactor().monotonic())
        current_z = self.toolhead.get_position()[2]
        recovery_z = min(max(start[2], current_z + 2.0), status['axis_maximum'][2])
        logging.warning('Probe recovery: start_z=%.6f current_z=%.6f recovery_z=%.6f',
                        start[2], self.toolhead.get_position()[2], recovery_z)
        if current_z < recovery_z - .001:
            speed = self.session.param_helper.get_probe_params(gcmd)['lift_speed']
            self.toolhead.manual_move([None, None, recovery_z], speed)
        self.toolhead.dwell(.050)
        self.toolhead.wait_moves()
        if not self.safe(gcmd, start):
            raise self.printer.command_error(ERROR)
        self.wrapper._lower_probe()  # Existing activate_gcode / G4 P200
        self.reactivations += 1
        if self.triggered() or not self.safe(gcmd, start):
            return False
        self.toolhead.dwell(.020)
        return not self.triggered() and self.safe(gcmd, start)

    def run_probe(self, gcmd):
        if gcmd.get_command() not in ('BED_MESH_CALIBRATE', 'BED_MESH_CALIBRATE_BASE'):
            return self.original(gcmd)
        start = list(self.toolhead.get_position())
        previous_count = len(self.session.results)
        used = 0
        try:
            while True:
                try:
                    result = self.original(gcmd)
                    if used:
                        self.recoveries += 1
                        logging.info('Probe recovery: point completed at XY=%s; samples=%s',
                                     start[:2], self.session.param_helper.get_probe_params(gcmd)['samples'])
                    return result
                except self.printer.command_error as exc:
                    if str(exc) != ERROR:
                        raise
                    # The original averaging helper discards its local samples
                    # on exception. Its completed-point results must stay intact.
                    if len(self.session.results) != previous_count:
                        raise
                    while True:
                        if used >= self.attempts or not self.safe(gcmd, start):
                            raise
                        used += 1
                        self.printer.lookup_object('gcode').respond_raw(
                            'echo: Probe measurement error - redeploying probe (%d/%d)'
                            % (used, self.attempts))
                        logging.warning('Probe recovery: point restart %d/%d at %s',
                                        used, self.attempts, start[:3])
                        self.wrapper.homing_helper.clear_trigger_positions()
                        if self.recover(gcmd, start):
                            self.printer.lookup_object('gcode').respond_raw('// PROBE_RECOVERY_SAMPLING')
                            logging.info('Probe recovery: signal open; restarting all %s samples at XY=%s Z=%.6f',
                                         self.session.param_helper.get_probe_params(gcmd)['samples'],
                                         start[:2], self.toolhead.get_position()[2])
                            break
        except Exception:
            if used and not self.printer.is_shutdown():
                self.wrapper._raise_probe()
            raise

def load_config(config):
    return ProbeAutoRecovery(config)
