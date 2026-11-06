import unittest
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import tempfile
import shutil
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lugo_install', ROOT/'maintenance/install_panels.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class LugoReleaseTests(unittest.TestCase):
    def test_runtime_backup_idempotence_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root/'screen/panels'
            target.mkdir(parents=True)
            for name in installer.RUNTIME:
                p = target.parent/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('# original runtime')
            source = ROOT/'panels/common'
            backup = root/'backup'
            installer.install(source, target, backup, check=True)
            self.assertFalse(backup.exists())
            installer.install(source, target, backup)
            times = {name: (target.parent/name).stat().st_mtime_ns for name in installer.RUNTIME}
            installer.install(source, target, backup)
            for name in installer.RUNTIME:
                self.assertEqual((backup/'runtime'/name).read_text(), '# original runtime')
                self.assertEqual((target.parent/name).read_bytes(), (source.parent/'runtime'/name).read_bytes())
                self.assertEqual(times[name], (target.parent/name).stat().st_mtime_ns)

    def test_invalid_runtime_prevents_panel_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'payload/common'
            shutil.copytree(ROOT/'panels/common', source)
            shutil.copytree(ROOT/'panels/runtime', source.parent/'runtime')
            (source.parent/'runtime'/installer.RUNTIME[-1]).write_text('def broken(')
            target = root/'screen/panels'
            target.mkdir(parents=True)
            (target/'extrude.py').write_text('# untouched')
            with self.assertRaises(SyntaxError):
                installer.install(source, target, root/'backup')
            self.assertEqual((target/'extrude.py').read_text(), '# untouched')
            self.assertFalse((root/'backup').exists())

    def test_scrollbar_policy_retains_scroll_adjustments(self):
        tree = ast.parse((ROOT/'panels/runtime/ks_includes/widgets/scroll.py').read_text())
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'set_policy')
        call = Mock()
        gtk = SimpleNamespace(ScrolledWindow=SimpleNamespace(set_policy=call), PolicyType=SimpleNamespace(EXTERNAL=3))
        ns = {'Gtk': gtk}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<scroll>', 'exec'), ns)
        widget = object()
        ns['set_policy'](widget, 0, 1)
        call.assert_called_once_with(widget, 3, 3)
        self.assertNotIn('set_kinetic_scrolling(False)', ast.unparse(tree))

    def test_network_cache_disappearing_ap_and_connect(self):
        import ast, time, logging
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock
        source=(ROOT/'panels/runtime/ks_includes/sdbus_nm.py').read_text(encoding='utf-8');tree=ast.parse(source)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SdbusNm')
        methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('get_networks','get_connected_bssid','rescan')]
        class Gone(Exception):pass
        reads=[]
        def ap(path):
         reads.append(path)
         if path=='gone':raise Gone('removed')
         return SimpleNamespace(ssid=path.encode(),frequency=2400,rsn_flags=0,wpa_flags=0,flags=0,strength=70,hw_address=path)
        enums=SimpleNamespace(DeviceState=SimpleNamespace(DISCONNECTED=30,ACTIVATED=100))
        ns=dict(time=time,logging=logging,AccessPoint=ap,WifiChannels=lambda f:(2.4,1),get_encryption=lambda f:'Open',DbusUnknownMethodError=Gone,DbusUnknownObjectError=Gone,enums=enums)
        for method in methods:exec(compile(ast.Module(body=[method],type_ignores=[]),'<test>','exec'),ns)
        obj=SimpleNamespace(get_selected_interface=lambda:'wlan0',get_known_networks=Mock(return_value=[{'SSID':'one'}]),wlan_device=SimpleNamespace(access_points=['one','gone','two']))
        result=ns['get_networks'](obj)
        assert len(result)==2 and result[0]['known']
        assert ns['get_networks'](obj) is result
        assert len(reads)==3 and obj.get_known_networks.call_count==1
        obj.wlan_device.request_scan=Mock();obj.get_interface_status=lambda:50
        ns['rescan'](obj);obj.wlan_device.request_scan.assert_not_called()
        obj.get_interface_status=lambda:100
        ns['rescan'](obj);obj.wlan_device.request_scan.assert_called_once()
        net=ast.parse((ROOT/'panels/common/network.py').read_text(encoding='utf-8'))
        connect=next(n for n in ast.walk(net) if isinstance(n,ast.FunctionDef) and n.name=='connect_network')
        exec(compile(ast.Module(body=[connect],type_ignores=[]),'<test>','exec'),ns)
        backend=SimpleNamespace(is_known=lambda s:True,get_bssid_from_ssid=lambda s:None,connect=Mock())
        panel=SimpleNamespace(deactivate=Mock(),activate=Mock(),sdbus_nm=backend,network_rows={})
        ns['connect_network'](panel,None,'one')
        panel.activate.assert_called_once_with(scan=False);backend.connect.assert_called_once_with('one')
        print('PASS single snapshot/cache, vanished AP, connection scan guard and connect without reload')
