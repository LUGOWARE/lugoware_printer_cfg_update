"""Progressive multi-sample probing with bounded trigger recovery."""
import logging
import math
from .probe import calc_probe_z_average

TOLERANCES = (0.030, 0.045, 0.060, 0.075, 0.090)

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
                'attempts': self.attempts, 'scope': 'multi_sample_probe_excluding_g28',
                'normal_path_extra_wait': False, 'recovery_lift': 2.0,
                'sample_tolerances': list(TOLERANCES),
                'tolerance_retry_wait': 1.0, 'trigger_recovery_wait': 2.0,
                'trigger_recovery_batches_per_point': 1, 'g28_sampling': 'stock'}

    def safe(self, gcmd, start):
        fc = self.fast_cancel
        if self.printer.is_shutdown() or fc.requested or fc.cleaning:
            return False
        if gcmd.get_command() == 'G28':
            return False
        status = self.toolhead.get_status(self.printer.get_reactor().monotonic())
        if set('xyz') - set(status['homed_axes']):
            return False
        current = self.toolhead.get_position()
        if not all(math.isfinite(v) for v in current[:3] + start[:3]):
            return False
        if any(abs(current[i] - start[i]) > .001 for i in (0, 1)):
            return False
        return (status['axis_minimum'][2] <= current[2] <= status['axis_maximum'][2]
                and start[2] <= status['axis_maximum'][2])

    def lift_and_wait(self, gcmd, start, delay):
        if not self.safe(gcmd, start):
            raise gcmd.error('Probe retry aborted: unsafe state')
        current = self.toolhead.get_position()
        target_z = current[2] + 2.0
        status = self.toolhead.get_status(self.printer.get_reactor().monotonic())
        if target_z > status['axis_maximum'][2]:
            raise gcmd.error('Probe retry aborted: insufficient Z clearance')
        speed = self.session.param_helper.get_probe_params(gcmd)['lift_speed']
        self.toolhead.manual_move([None, None, target_z], speed)
        self.toolhead.dwell(delay)
        self.toolhead.wait_moves()
        if not self.safe(gcmd, start):
            raise gcmd.error('Probe retry aborted: unsafe state')
        logging.info('Probe retry lift: command=%s from_z=%.6f to_z=%.6f wait=%.1f',
                     gcmd.get_command(), current[2], target_z, delay)

    def triggered(self):
        self.toolhead.wait_moves()
        return bool(self.wrapper.query_endstop(self.toolhead.get_last_move_time()))

    def recover(self, gcmd, start):
        self.printer.lookup_object('gcode').respond_raw(
            'echo: Probe trigger error - recovering and retrying.')
        self.lift_and_wait(gcmd, start, 2.0)
        for cycle in range(1, self.attempts + 1):
            if not self.safe(gcmd, start):
                raise gcmd.error('Probe retry aborted: unsafe state')
            self.wrapper._raise_probe()
            self.toolhead.dwell(.050)
            self.wrapper._lower_probe()  # Existing activate_gcode / G4 P200
            self.toolhead.wait_moves()
            self.reactivations += 1
            logging.warning('Probe recovery: redeployment %d/%d at Z=%.6f',
                            cycle, self.attempts, self.toolhead.get_position()[2])
        if not self.safe(gcmd, start) or self.triggered():
            return False
        self.toolhead.dwell(.020)
        return self.safe(gcmd, start) and not self.triggered()

    def sample_point(self, gcmd):
        # Each point starts at 0.030; rejected sets never contribute samples.
        session = self.session
        if session.hw_probe_session is None:
            session._probe_state_error()
        params = session.param_helper.get_probe_params(gcmd)
        start = list(self.toolhead.get_position())
        xy = start[:2]
        for attempt, tolerance in enumerate(TOLERANCES, 1):
            positions = []
            for sample in range(params['samples']):
                positions.append(session._probe(gcmd))
                # Complete all samples before deciding whether to retry this point.
                if sample + 1 < params['samples']:
                    z = self.toolhead.get_position()[2]
                    self.toolhead.manual_move(
                        xy + [z + params['sample_retract_dist']], params['lift_speed'])
            spread = max(p.bed_z for p in positions) - min(p.bed_z for p in positions)
            accepted = math.isfinite(spread) and spread <= tolerance + 1.e-9
            logging.info('Probe tolerance: XY=%s attempt=%d/5 tolerance=%.3f spread=%.6f accepted=%s',
                         xy, attempt, tolerance, spread, accepted)
            if accepted:
                session.results.append(calc_probe_z_average(positions, params['samples_result']))
                return
            if attempt == len(TOLERANCES):
                raise gcmd.error('Probe samples exceed samples_tolerance')
            gcmd.respond_info('Probe samples exceed tolerance. Retrying... '
                              '(attempt %d/5, tolerance %.3f mm)' %
                              (attempt + 1, TOLERANCES[attempt]))
            self.printer.lookup_object('gcode').respond_raw(
                'echo: Probe tolerance exceeded (%d/5) - retrying.' % attempt)
            self.lift_and_wait(gcmd, start, 1.0)
            self.printer.lookup_object('gcode').respond_raw('// PROBE_RECOVERY_SAMPLING')

    def run_probe(self, gcmd):
        if (gcmd.get_command() == 'G28'
                or self.session.param_helper.get_probe_params(gcmd)['samples'] < 2):
            return self.original(gcmd)
        start = list(self.toolhead.get_position())
        previous_count = len(self.session.results)
        recovered = False
        try:
            while True:
                try:
                    result = self.sample_point(gcmd)
                    if recovered:
                        self.recoveries += 1
                    return result
                except self.printer.command_error as exc:
                    if (str(exc) != ERROR or recovered
                            or len(self.session.results) != previous_count):
                        raise
                    recovered = True  # One bounded two-cycle recovery per point.
                    self.wrapper.homing_helper.clear_trigger_positions()
                    if not self.recover(gcmd, start):
                        raise
                    self.printer.lookup_object('gcode').respond_raw('// PROBE_RECOVERY_SAMPLING')
                    logging.info('Probe recovery: restarting point at tolerance=0.030 XY=%s', start[:2])
        except Exception:
            if recovered and not self.printer.is_shutdown():
                self.wrapper._raise_probe()
            raise


def load_config(config):
    return ProbeAutoRecovery(config)
