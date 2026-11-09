import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel
from ks_includes import first_run_state as state
TEXT={
'ko':['처음 설정','언어 선택','네트워크 연결','시간대 설정','다음','이전','네트워크 설정 열기','시간대 설정 열기','설정 완료','유선 연결을 사용하거나 Wi-Fi를 설정하세요.\n네트워크 없이도 진행할 수 있습니다.','사용할 지역의 시간대를 선택하세요.','출고 초기화가 완료되지 않았습니다.\n공장 초기화 프로그램으로 다시 진행해 주세요.'],
'en':['Welcome','Language','Network','Time zone','Next','Back','Open network settings','Open time zone settings','Finish setup','Use Ethernet or configure Wi-Fi.\nYou can continue offline.','Select the time zone for your location.','Factory reset is incomplete.\nRun the factory tool again.'],
'zh':['首次设置','选择语言','网络连接','时区设置','下一步','上一步','打开网络设置','打开时区设置','完成设置','使用有线网络或配置 Wi-Fi。\n也可以离线继续。','请选择您所在地区的时区。','出厂重置未完成。\n请重新运行工厂重置工具。']}
class Panel(ScreenPanel):
    def __init__(self,screen,title):
        super().__init__(screen,title)
        self.step=min(2,max(0,int(state.read().get('step',0))))
        self.box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        self.box.set_hexpand(True);self.box.set_vexpand(True)
        self.box.set_size_request(-1,max(400,getattr(screen,'height',800)-160))
        self.box.get_style_context().add_class('factory-wizard')
        css=Gtk.CssProvider();css.load_from_data(b'.factory-wizard button { background-image:none; background-color:#252525; border:0; border-radius:4px; padding:12px; } .factory-wizard button:active { background-color:#424242; }')
        Gtk.StyleContext.add_provider_for_screen(self.content.get_screen(),css,Gtk.STYLE_PROVIDER_PRIORITY_USER)
        for method in ('set_margin_start','set_margin_end','set_margin_top','set_margin_bottom'):getattr(self.box,method)(18)
        self.content.add(self.box);self.draw()
    def tr(self):
        lang=self._config.get_main_config().get('language','en').lower()
        return TEXT.get(lang.split('_')[0].split('-')[0],TEXT['en'])
    def button(self,text,callback):
        b=Gtk.Button(label=text);b.set_size_request(-1,64);b.connect('clicked',callback);return b
    def draw(self):
        for c in self.box.get_children():self.box.remove(c)
        t=self.tr();title=Gtk.Label(label=t[0]);title.get_style_context().add_class('title');self.box.pack_start(title,False,False,8)
        self.box.pack_start(Gtk.Label(label=f'{self.step+1} / 3 — {t[self.step+1]}'),False,False,8)
        if state.read().get('status') in ('resetting','failed'):
            self.box.pack_start(Gtk.Label(label=t[11],wrap=True,justify=Gtk.Justification.CENTER),True,True,0);self.box.show_all();return
        center=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20);center.set_valign(Gtk.Align.CENTER)
        self.box.pack_start(center,True,True,0)
        if self.step==0:
            from ks_includes.lugo_language_names import language_name
            combo=Gtk.ComboBoxText()
            for lang in self._config.lang_list:combo.append(lang,language_name(lang))
            combo.set_active_id(self._config.get_main_config().get('language','en'))
            combo.set_size_request(-1,70);combo.connect('changed',self.language);center.pack_start(combo,False,False,0)
        else:
            center.pack_start(Gtk.Label(label=t[8+self.step],wrap=True,justify=Gtk.Justification.CENTER),False,False,0)
            panel='network' if self.step==1 else 'timezone'
            center.pack_start(self.button(t[5+self.step],lambda w:self._screen.show_panel(panel)),False,False,0)
        buttons=Gtk.Box(spacing=12)
        if self.step:buttons.pack_start(self.button(t[5],lambda w:self.advance(-1)),True,True,0)
        buttons.pack_start(self.button(t[8] if self.step==2 else t[4],lambda w:self.advance(1)),True,True,0)
        self.box.pack_end(buttons,False,False,0);self.box.show_all()
    def language(self,combo):
        code=combo.get_active_id()
        if code:self._screen.change_language(combo,code)
    def advance(self,direction):
        self.step+=direction
        if self.step>2:
            state.save({'status':'complete','step':2});self._screen.state_ready(wait=False);return
        state.save({'status':'pending','step':self.step});self.draw()
