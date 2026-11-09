import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"maintenance/recovery"))
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch

gtk=Obj(ResponseType=Obj(OK=1,REJECT=2,CANCEL=3),Label=object)
fake={'gi':Obj(), 'gi.repository':Obj(Gtk=gtk,GLib=Obj(timeout_add_seconds=lambda *a:None)),
      'panels':Obj(), 'panels.recovery':Obj(tr=lambda screen,text:text)}
with patch.dict(sys.modules,fake):
    spec=importlib.util.spec_from_file_location('recovery_files_tested',Path(__file__).resolve().parents[2]/'maintenance/recovery/recovery_files.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def result(name='sub/part.gcode',session='abc',available=True):
    return {'state':{'available':available},'record':{'filename':name,'session':session}}

class Tests(unittest.TestCase):
    def make(self):
        self.sent=[];self.opened=[];self.errors=[];self.panels=[];self.dialogs=[]
        screen=Obj(_ws=Obj(send_method=lambda *args:self.sent.append(args) or True),
                   show_popup_message=self.errors.append,show_panel=lambda *a:self.panels.append(a))
        panel=Obj(_screen=screen,_gtk=Obj(remove_dialog=lambda d:None),flowbox=Obj(get_children=lambda:[]),
                  open_print_info=lambda w,n:self.opened.append(n))
        r=mod.RecoveryFiles(panel);r.active=True
        r.dialog=lambda *a:self.dialogs.append(a)
        return r

    def test_full_path_match_not_basename(self):
        self.assertTrue(mod.matches(result(),'gcodes/sub/part.gcode'))
        self.assertFalse(mod.matches(result(),'other/part.gcode'))
        self.assertFalse(mod.matches(result(available=False),'sub/part.gcode'))

    def test_badge_targets_replaced_thumbnail_label(self):
        r=self.make();r.result=result();labels=[]
        child=Obj(_recovery_name_label=None,_recovery_filename='sub/part.gcode',_recovery_original='part',
                  _recovery_button=Obj(live_label=Obj(set_markup=labels.append)))
        with patch.dict(sys.modules,{'ks_includes':Obj(),'ks_includes.KlippyGtk':Obj(find_widget=lambda w,t:w.live_label)}):
            r.update_badge(child)
        self.assertIn('!</span>',labels[-1])
        self.assertTrue(labels[-1].endswith('part'))

    def test_regular_file_opens_original_info_only(self):
        r=self.make();r.select(None,'new.gcode');self.sent[-1][2]({'result':result()})
        self.assertEqual(self.opened,['new.gcode']);self.assertFalse(self.dialogs)

    def test_candidate_choose_close_preserves_record(self):
        r=self.make();r.select(None,'sub/part.gcode');self.sent[-1][2]({'result':result()})
        self.dialogs[-1][-1](None,gtk.ResponseType.CANCEL)
        self.assertFalse(self.opened);self.assertFalse(self.panels)
        self.assertEqual([v[1]['action'] for v in self.sent],['status'])

    def test_resume_verifies_session_then_opens_panel(self):
        r=self.make();r.choose('sub/part.gcode','abc');self.dialogs[-1][-1](None,gtk.ResponseType.OK)
        self.sent[-1][2]({'result':result()})
        self.assertEqual(self.panels[0][0],'recovery');self.assertFalse(self.opened)

    def test_changed_session_cannot_resume(self):
        r=self.make();r.choose('sub/part.gcode','abc');self.dialogs[-1][-1](None,gtk.ResponseType.OK)
        self.sent[-1][2]({'result':result(session='new')})
        self.assertFalse(self.panels);self.assertTrue(self.errors)

    def test_fresh_requires_confirmation_and_discard_success(self):
        r=self.make();r.choose('sub/part.gcode','abc');self.dialogs[-1][-1](None,gtk.ResponseType.REJECT)
        self.assertFalse(self.sent)
        self.dialogs[-1][-1](None,gtk.ResponseType.OK)
        self.assertEqual(self.sent[-1][1],{'action':'discard','session':'abc'})
        self.assertFalse(self.opened)
        self.sent[-1][2]({'result':result(available=False)})
        self.assertEqual(self.opened,['sub/part.gcode'])
        self.assertTrue(all(call[0]=='printer.lugo_recovery.control' for call in self.sent))

    def test_discard_error_cannot_start_fresh(self):
        r=self.make();r.confirm_fresh('sub/part.gcode','abc');self.dialogs[-1][-1](None,gtk.ResponseType.OK)
        self.sent[-1][2]({'error':{'message':'stale'}})
        self.assertFalse(self.opened);self.assertEqual(self.errors,['stale'])

    def test_late_click_response_after_leaving_is_ignored(self):
        r=self.make();r.select(None,'sub/part.gcode');callback=self.sent[-1][2];r.deactivate()
        callback({'result':result()})
        self.assertFalse(self.opened);self.assertFalse(self.dialogs)

if __name__=='__main__':unittest.main()
