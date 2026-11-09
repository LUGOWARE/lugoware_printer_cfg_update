import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"maintenance/recovery"))
import copy
import json
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch
import lugo_recovery as m


class Request:
    def __init__(self, **kw): self.kw = kw
    def get_str(self, key, default=None): return self.kw.get(key, default)
    def get_int(self, key, default=None): return self.kw.get(key, default)
    def send(self, result): self.result = result
    def error(self, message): return ValueError(message)


class Tests(unittest.TestCase):
    def make(self):
        d = m.Recovery.__new__(m.Recovery)
        d.boot = 'new'; d.running = False; d.write_error = ''; d.pending = queue.Queue(1)
        d.record = {'version': 1, 'boot': 'old', 'session': 'test', 'status': 'interrupted',
                    'snapshot': {'gcode_move': {'gcode_position': [1, 2, 3, 4]}}, 'history': []}
        d.reactor = Obj(monotonic=lambda: 20, register_timer=lambda *a: None)
        d.status = lambda name, now: {'state': 'standby'} if name == 'print_stats' else {'filament_detected': True}
        return d

    def test_candidates(self):
        d = self.make()
        self.assertTrue(m.candidate(d.record, d.boot))
        for state in m.TERMINAL:
            d.record['status'] = state
            self.assertFalse(m.candidate(d.record, d.boot))
        d.record.update(status='recording', boot='new')
        self.assertFalse(m.candidate(d.record, d.boot))
        self.assertTrue(m.candidate(d.record, 'next-boot'))

    def test_atomic_and_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'current.json'; data = self.make().record
            m.atomic_json(p, data)
            self.assertEqual(m.read_record(p), data)
            with patch.object(m.os, 'replace', side_effect=OSError('disk')):
                with self.assertRaises(OSError): m.atomic_json(p, dict(data, status='discarded'))
            self.assertEqual(m.read_record(p), data)
            p.write_text('{broken')
            self.assertIsNone(m.read_record(p))

    def test_queue_bounded_and_copy(self):
        d = self.make()
        for i in range(200):
            d.record['sequence'] = i; d.submit()
        d.record['sequence'] = 999
        self.assertEqual(d.pending.qsize(), 1)
        self.assertEqual(d.pending.get()['sequence'], 199)

    def test_review_no_motion(self):
        d = self.make(); q = Request(action='review', session='test', tool=1, z_unchanged=1, completed_layer=5)
        d.control(q)
        self.assertFalse(d.record['review']['motion_enabled'])
        self.assertEqual(d.record['review']['tool'], 1)
        self.assertEqual(d.record['review']['completed_layer'], 5)
        self.assertEqual(d.pending.qsize(), 1)

    def test_wrong_sensor_stale_and_printing(self):
        d = self.make()
        for args in (dict(tool=-1), dict(session='stale'), dict(z_unchanged=0)):
            kw=dict(action='review',session='test',tool=1,z_unchanged=1,completed_layer=5);kw.update(args)
            with self.assertRaises(ValueError): d.control(Request(**kw))
        d.running=True
        with self.assertRaises(ValueError): d.control(Request(action='discard',session='test'))
        self.assertNotIn('review', d.record)

    def test_discard_deletes_files_and_blocks_stale_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            d=self.make();d.folder=Path(directory);d.path=d.folder/'current.json'
            d.io_lock=threading.Lock();d.deleted_sessions=set();d.last_written=None;d.archived_states=set()
            d.record['session']='abcdef';old=copy.deepcopy(d.record)
            m.atomic_json(d.path,old);m.atomic_json(d.folder/'abcdef.json',old)
            m.atomic_json(d.folder/'123456.json',dict(old,session='123456'))
            d.control(Request(action='discard',session='abcdef'))
            self.assertIsNone(d.record)
            self.assertFalse(d.path.exists());self.assertFalse((d.folder/'abcdef.json').exists())
            self.assertTrue((d.folder/'123456.json').exists())
            d.persist_record(old)
            self.assertFalse(d.path.exists())

    def test_periodic_write_once_duplicate_skipped_terminal_archived(self):
        with tempfile.TemporaryDirectory() as directory:
            d=self.make();d.folder=Path(directory);d.path=d.folder/'current.json'
            d.io_lock=threading.Lock();d.deleted_sessions=set();d.last_written=None;d.archived_states=set()
            data=dict(d.record,session='abcdef',status='recording')
            with patch.object(m,'atomic_json',wraps=m.atomic_json) as write:
                d.persist_record(data);self.assertEqual(write.call_count,1)
                d.persist_record(data);self.assertEqual(write.call_count,1)
                data['sequence']=2;d.persist_record(data);self.assertEqual(write.call_count,2)
                data['status']='completed';d.persist_record(data);self.assertEqual(write.call_count,4)

    def test_shutdown_keeps_pre_failure_position(self):
        d=self.make();d.running=True;before=copy.deepcopy(d.record['snapshot'])
        d.printer=Obj(get_state_message=lambda:('Lost communication','shutdown'))
        d.shutdown()
        self.assertEqual(d.record['snapshot'],before)
        self.assertEqual(d.record['status'],'interrupted')
        self.assertFalse(d.running)

    def test_terminal_callbacks_do_not_mask_error(self):
        d=self.make();d.record['boot']=d.boot;d.record['status']='recording'
        calls=[]
        st=Obj(note_complete=lambda:calls.append('complete'),note_cancel=lambda:calls.append('cancel'),note_error=lambda error:calls.append(error))
        d.printer=Obj(lookup_object=lambda name:st)
        d.ready();st.note_error('fault');st.note_cancel()
        self.assertEqual(calls,['fault','cancel'])
        self.assertEqual(d.record['status'],'interrupted')
        d.record['status']='recording';st.note_complete()
        self.assertEqual(d.record['status'],'completed')

    def test_print_observation_tracks_tool_mesh_and_position(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'test.gcode';source.write_text('G1 X1\n')
            d=self.make();d.record=None;d.recovering=False
            stats={'state':'printing','filename':'test.gcode','info':{'current_layer':3}}
            d.status=lambda name,now:stats if name=='print_stats' else {}
            d.printer=Obj(lookup_object=lambda name:Obj(sdcard_dirname=directory),is_shutdown=lambda:False)
            snapshot={'recorded_at':100.,'print_stats':stats,'virtual_sdcard':{'file_position':6},
                      'motion_report':{'live_position':[1,2,3,4]},'gcode_move':{'gcode_position':[1,2,3.2,4]},
                      'gcode_macro TOOL_STATE':{'active_tool':2},'fast_cancel':{'phase':'docked'},
                      'active_mesh':{'points':[[0,0],[0,0]]}}
            d.snapshot=lambda now:copy.deepcopy(snapshot)
            d.tick(20)
            self.assertTrue(d.running)
            self.assertEqual(d.record['snapshot']['active_mesh'],snapshot['active_mesh'])
            self.assertEqual(d.record['history'][-1]['tool'],2)
            self.assertEqual(d.record['history'][-1]['file_position'],6)
            stats['state']='cancelled';d.tick(21)
            self.assertFalse(d.running)
            self.assertEqual(d.pending.get()['status'],'cancelled')


if __name__ == '__main__': unittest.main()
