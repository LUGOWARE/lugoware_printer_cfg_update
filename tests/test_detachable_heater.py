import importlib.util, unittest
from types import SimpleNamespace as N
from pathlib import Path
spec=importlib.util.spec_from_file_location('adapter',Path(__file__).resolve().parents[1]/'maintenance/toolhead_variant/detachable_heater_sensor.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Tests(unittest.TestCase):
 def setUp(self):
  self.now=10.;self.state='connected';self.tool=1;self.print_state='standby';self.filename='a';self.shutdown=[];self.commands=[];self.callbacks=[]
  self.cancel=N(requested=False,cleaning=False)
  self.pause=N(is_paused=False)
  self.objects={'gcode_macro TOOL_STATE':N(get_status=lambda t:{'active_tool':self.tool}), 'print_stats':N(get_status=lambda t:{'state':self.print_state,'filename':self.filename}), 'fast_cancel':self.cancel,'pause_resume':self.pause}
  p=N(lookup_object=lambda key,default=None:self.objects.get(key,default),register_event_handler=lambda *a:None,command_error=RuntimeError,invoke_shutdown=self.shutdown.append,is_shutdown=lambda:bool(self.shutdown))
  g=N(register_command=lambda *a, **kw:None,respond_info=lambda *a:None,run_script=self.commands.append)
  reactor=N(monotonic=lambda:self.now,register_callback=self.callbacks.append)
  source=N(printer=p,gcode=g,reactor=reactor,get_status=lambda t:{'state':self.state},last=1.)
  class Heater:
   target_temp=0.;last_pwm_value=0.;control=None
   def set_temp(h,v):h.target_temp=v
   def alter_target(h,v):h.target_temp=v
   def get_status(h,t):return {}
   def temperature_callback(h,t,v):pass
   def set_pwm(h,t,v):h.last_pwm_value=v;h.pwm_time=t
  self.h=Heater();self.h.mcu_pwm=N(get_mcu=lambda:N(estimated_print_time=lambda t:t))
  self.a=m.DetachableHeaterSensor(source,None);self.a.setup_minmax(0,300);self.a.setup_callback(self.h.temperature_callback);self.a.valid_samples=9
  self.a.nozzle_heater=N(target_temp=0.,control=None)
  self.a.manual_controls=()  # Manual target linking is exercised separately.
  self.h.set_temp(200);self.h.last_pwm_value=.7
 def detach(self):
  self.state='disconnected';self.a.sample(self.now,'disconnected',None)
 def reconnect(self,elapsed=1.):
  self.now+=elapsed;self.state='connected'
  for i in range(9):self.a.sample(self.now,'connected',25.)
  self.a.watchdog(self.now)
 def test_first_sample_off(self):
  self.detach();self.assertEqual((self.h.target_temp,self.h.last_pwm_value),(0,0));self.assertFalse(self.shutdown)
 def test_reconnect(self):
  self.detach();self.reconnect();self.assertEqual(self.h.target_temp,200)
 def test_expired(self):
  self.detach();self.reconnect(5.);self.assertEqual(self.h.target_temp,0)
 def test_not_reset_by_open_samples(self):
  self.detach();self.now+=4;self.detach();self.reconnect(1.1);self.assertEqual(self.h.target_temp,0)
 def test_unstable(self):
  self.detach();self.state='connected';self.a.valid_samples=8;self.a.watchdog(self.now);self.assertEqual(self.h.target_temp,0)
 def test_zero_command(self):
  self.detach();self.h.set_temp(0);self.reconnect();self.assertEqual(self.h.target_temp,0)
 def test_alter_zero(self):
  self.detach();self.h.alter_target(0);self.reconnect();self.assertEqual(self.h.target_temp,0)
 def test_other_tool(self):
  self.detach();self.tool=2;self.reconnect();self.assertEqual(self.h.target_temp,0)
 def test_unknown_tool(self):
  self.tool=-1;self.detach();self.reconnect();self.assertEqual(self.h.target_temp,0)
 def test_cancel(self):
  self.detach();self.cancel.requested=True;self.reconnect();self.assertEqual(self.h.target_temp,0)
 def test_filename_changed(self):
  self.detach();self.filename='b';self.reconnect();self.assertEqual(self.h.target_temp,0)
 def test_print_finished(self):
  self.print_state='printing';self.detach();self.print_state='complete';self.reconnect();self.assertEqual(self.h.target_temp,0)
 def test_pause_no_resume(self):
  self.print_state='printing';self.detach();self.callbacks[0](self.now);self.assertEqual(self.commands,['PAUSE']);self.print_state='paused';self.reconnect();self.assertEqual(self.h.target_temp,200);self.assertEqual(self.commands,['PAUSE'])
 def test_short(self):
  self.a.sample(self.now,'short_circuit',None);self.assertTrue(self.shutdown);self.assertEqual(self.h.target_temp,0)
 def test_hot_idle(self):
  self.h.set_temp(0);self.h.last_pwm_value=0;self.a.sample(self.now,'connected',301);self.assertTrue(self.shutdown)
 def test_short_after_detach(self):
  self.detach();self.a.sample(self.now,'short_circuit',None);self.assertTrue(self.shutdown)
 def test_stale(self):
  self.detach();self.state='stale';self.a.watchdog(self.now);self.assertTrue(self.shutdown)
 def test_idle_detach(self):
  self.h.set_temp(0);self.h.last_pwm_value=0;self.detach();self.reconnect();self.assertEqual(self.h.target_temp,0);self.assertFalse(self.shutdown)

 def test_prime_uses_configured_margin_and_timeout(self):
  self.h.set_temp(230)
  self.cancel.stop_wait = lambda: False
  self.a.source.prime_temperature_margin = 12.
  self.a.source.prime_timeout = 1.
  self.a.source.get_status = lambda now: {
      'state': 'connected', 'temperature': 217. if now < 10.4 else 218.}
  self.a.source.reactor.pause = lambda until: until
  gcmd = N(get_float=lambda key, **limits: {'TARGET': 230.}[key], error=RuntimeError)
  self.a.wait_for_prime(gcmd)
  self.assertEqual(self.h.target_temp, 230.)
  self.a.source.prime_timeout = .2
  with self.assertRaisesRegex(RuntimeError, '218.0 C before prime'):
   self.a.wait_for_prime(gcmd)
  self.assertEqual(self.h.target_temp, 0.)

 def test_prime_sensor_fault_aborts_and_turns_off_heater(self):
  self.h.set_temp(230)
  self.cancel.stop_wait = lambda: False
  self.a.source.prime_temperature_margin = 15.
  self.a.source.prime_timeout = 60.
  self.a.source.get_status = lambda now: {'state': 'short_circuit'}
  gcmd = N(get_float=lambda key, **limits: {'TARGET': 230.}[key], error=RuntimeError)
  with self.assertRaisesRegex(RuntimeError, 'short_circuit'):
   self.a.wait_for_prime(gcmd)
  self.assertEqual(self.h.target_temp, 0.)

if __name__=='__main__':unittest.main(verbosity=2)

