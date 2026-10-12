"""Manual GTK integration smoke test; never sends printer commands.

Run with the KlipperScreen Python environment on a Linux graphical session:
DISPLAY=:0 ~/.KlipperScreen-env/bin/python tests/gtk_layout_smoke.py
Actual stock buttons/menu/move code is loaded from --screen-dir. The main
heater/graph area is a static fixture; temperature and motion services are absent.
"""
import sys,types,importlib.util,gettext,time,configparser,json,os,argparse
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from jinja2 import Environment
parser=argparse.ArgumentParser()
parser.add_argument('--screen-dir',type=Path,default=Path.home()/'KlipperScreen')
parser.add_argument('--output',type=Path)
parser.add_argument('--font-size',default='medium',choices=('small','medium','large','extralarge','max'))
args=parser.parse_args()
if args.output: args.output.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(args.screen_dir))
sys.path.insert(0,str(root/'maintenance'))
import ks_includes
import lugo_layout
sys.modules['ks_includes.lugo_layout']=lugo_layout
from lugo_i18n import Translations
import ks_includes.KlippyGtk as gtk_module
gtk_module.format_label=lugo_layout.format_button
gettext.NullTranslations().install()
from panels.move import Panel as MovePanel
from panels.main_menu import Panel as MainPanel

class MainFixture(MainPanel):
 def create_left_panel(self):
  box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
  box.pack_start(Gtk.Label(label='Extruder                      28.0째C'),False,False,12)
  box.pack_start(Gtk.Label(label='Heater Bed                    28.0째C'),False,False,12)
  graph=Gtk.DrawingArea();graph.set_vexpand(True);box.pack_start(graph,True,True,0)
  self.left_panel=box;return box

class Config:
 def __init__(self):
  self.cfg=configparser.ConfigParser();self.cfg.read_dict({'main':{'font_size':args.font_size}})
 def get_main_config(self):return self.cfg['main']
 def get_config(self):return self.cfg
class Printer:
 available_commands=[]
 def get_printer_status_data(self):return {'printer':{'temperature_devices':{'count':0},'extruders':{'count':0}}}
 def get_config_section_list(self):return []
 def get_config_section(self,key):return {'max_velocity':300,'kinematics':'cartesian'} if key=='printer' else {}

def load(name):
 spec=importlib.util.spec_from_file_location('fixture_'+name,root/'panels/common'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.Panel
PreparePanel=load('tool_prepare');ExtrudePanel=load('extrude');TemperaturePanel=load('tool_temperature')
noop=lambda *a,**k:None
failures=[]
checked=0
for path in sorted((root/'translations').glob('*.json')):
 lang=path.stem
 if os.environ.get("LOCALES") and lang not in os.environ["LOCALES"].split(","): continue
 print(lang,flush=True)
 upstream=gettext.translation('KlipperScreen',str(args.screen_dir/'ks_includes/locales'),languages=[lang],fallback=True)
 tr=Translations(upstream,lang,root/'translations');tr.install()
 for width,height in ((480,800),(800,480)):
  config=Config();screen=types.SimpleNamespace(width=width,height=height,vertical_mode=height>width,theme='material-darker',_config=config,files=None,printer=Printer(),_confirm_send_action=noop,_go_to_submenu=noop,screensaver=types.SimpleNamespace(reset_timeout=noop),lock_screen=types.SimpleNamespace(reset_timeout=noop),state=types.SimpleNamespace(connected=True),server_info={'warnings':[],'failed_components':[],'missing_klippy_requirements':[]})
  screen.env=Environment(extensions=['jinja2.ext.i18n']);screen.env.install_gettext_translations(tr)
  screen.gtk=gtk_module.KlippyGtk(screen)
  css=Gtk.CssProvider();css.load_from_data((args.screen_dir/'styles/base.css').read_text().replace('KS_FONT_SIZE',str(screen.gtk.font_size)).encode())
  Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,800)
  for cls in (MainFixture,MovePanel,PreparePanel,ExtrudePanel,TemperaturePanel):
   checked+=1
   win=Gtk.OffscreenWindow();win.set_size_request(width,height)
   frame=Gtk.Grid()
   header=Gtk.Label(label='FLEX4 '+_('Tool temperature control'));lugo_layout.fit_title(header);header.set_size_request(-1,36);header.set_vexpand(False)
   if cls is MainFixture:
    items=[]
    for i,(name,icon,panelname) in enumerate([('Move','move','move'),('Temperature','heat-up','temperature'),('Extrude','extrude','extrude'),('More','settings',None),('Print','print','print'),('Prepare','extruder','tool_prepare')]):
     items.append({str(i):{'name':_(name),'icon':icon,'panel':panelname,'enable':'True','style':None,'method':None}})
    panel=cls(screen,None,items)
   else:panel=cls(screen,None)
   panel.content.set_vexpand(True)
   footer=Gtk.Box(homogeneous=True)
   for icon in ('back','main','notifications','shutdown'):footer.add(screen.gtk.Button(icon,scale=.7))
   footer.set_size_request(screen.gtk.action_bar_width,screen.gtk.action_bar_height)
   if screen.vertical_mode:
    footer.set_vexpand(False);footer.set_hexpand(True)
    frame.attach(header,0,0,1,1);frame.attach(panel.content,0,1,1,1);frame.attach(footer,0,2,1,1)
   else:
    footer.set_orientation(Gtk.Orientation.VERTICAL);footer.set_hexpand(False);footer.set_vexpand(True)
    frame.attach(header,1,0,1,1);frame.attach(panel.content,1,1,1,1);frame.attach(footer,0,0,1,2)
   win.add(frame);win.show_all()
   for n in range(6):
    for iteration in range(100):
     if not Gtk.events_pending(): break
     Gtk.main_iteration()
    time.sleep(.015)
   if win.get_allocated_width()!=width or win.get_allocated_height()!=height:failures.append((lang,width,cls.__module__,win.get_size()))
   if footer.get_allocation().y+footer.get_allocated_height()>height:failures.append((lang,width,cls.__name__,'footer'))
   if cls is PreparePanel:
    def descendants(widget):
     yield widget
     if isinstance(widget,Gtk.Container):
      for child in widget.get_children(): yield from descendants(child)
    buttons=[w for w in descendants(panel.content) if isinstance(w,Gtk.Button) and any(d in (w.get_label() or '') for d in ('1.75','2.85'))]
    assert len(buttons)==2
    assert min(b.get_allocated_height() for b in buttons)>=64
    assert buttons[0].get_allocated_height()==buttons[1].get_allocated_height()
   if cls is MainFixture:
    adj=panel.menu_scroll.get_vadjustment()
    if adj.get_upper()>adj.get_page_size()+1:failures.append((lang,width,'main scroll',adj.get_upper(),adj.get_page_size()))
   if args.output:win.get_pixbuf().savev(str(args.output/(lang+'_'+str(width)+'_'+cls.__module__.replace('.','_')+'.png')),'png',[],[])
   win.destroy()
  screen.gtk.shutdown()
  Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),css)
print('FAILURES',failures)
assert not failures
print(f'{checked} panel layouts: bounds and main-menu scroll OK')



