from pathlib import Path
import unittest
import jinja2

class IdleTests(unittest.TestCase):
    def render(self, state='standby', target=220, previous=220, count=9):
        text=(Path(__file__).resolve().parents[1]/'maintenance/toolhead_variant/toolhead_auxiliary.cfg').read_text()
        body=text.split('[delayed_gcode turn_off_toolhead]')[1].split('gcode:',1)[1]
        env=jinja2.Environment(variable_start_string='{',variable_end_string='}')
        return env.from_string(body).render(printer={
            'print_stats':{'state':state},'heater_generic Toolhead':{'target':target},
            'gcode_macro TOOLHEAD_IDLE_STATE':{'last_target':previous,'idle_count':count}},
            action_respond_info=lambda text:'')
    def test_idle_timeout_and_reschedule(self):
        result=self.render()
        self.assertIn('SET_HEATER_TEMPERATURE HEATER=Toolhead TARGET=0',result)
        self.assertIn('UPDATE_DELAYED_GCODE ID=turn_off_toolhead DURATION=60',result)
    def test_printing_never_times_out(self):
        result=self.render(state='printing',count=100)
        self.assertNotIn('SET_HEATER_TEMPERATURE',result)
        self.assertIn('VARIABLE=idle_count VALUE=0',result)
    def test_target_change_resets(self):
        result=self.render(target=230,count=9)
        self.assertNotIn('SET_HEATER_TEMPERATURE',result)
        self.assertIn('VARIABLE=idle_count VALUE=0',result)
    def test_disabled_heater_resets(self):
        self.assertNotIn('SET_HEATER_TEMPERATURE',self.render(target=0,previous=0,count=9))
    def test_paused_matches_existing_nozzle_policy(self):
        self.assertIn('SET_HEATER_TEMPERATURE',self.render(state='paused'))
    def test_before_deadline(self):
        result=self.render(count=8)
        self.assertNotIn('SET_HEATER_TEMPERATURE',result)
        self.assertIn('VARIABLE=idle_count VALUE=9',result)
