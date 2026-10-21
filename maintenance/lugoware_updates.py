"""Report real installation progress, not just Git download completion."""
import json
import logging
from pathlib import Path
import re
import time


class UpdateStatus:
    def __init__(self, config):
        self.server = config.get_server()
        self.announcements = self.server.load_component(config, 'announcements')
        self.folder = Path.home() / '.local/share/lugoware'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.requests = {}
        self.timer = self.server.get_event_loop().register_timer(self.poll)
        self.server.register_event_handler('websockets:client_identified', self.client_identified)

    def client_identified(self, connection):
        # Moonraker may finish while the browser is still reconnecting.
        if connection.client_data.get('type') == 'web':
            self.server.get_event_loop().delay_callback(1., self.replay_completion, connection)

    def replay_completion(self, connection):
        if connection.is_closed:
            return
        try:
            ui = json.loads((self.folder / 'ui-install.json').read_text())
            if not ui.get('done') or not ui.get('message'):
                return
            manager = self.server.lookup_component('update_manager', None)
            if manager is not None and manager.cmd_helper.is_update_busy():
                return
            for channel, started in ui['channels'].items():
                if channel not in ('config', 'system'):
                    return
                state = json.loads((self.folder / (channel + '-status.json')).read_text())
                if state['state'] not in ('complete', 'failed') or int(state['run_id']) / 1e9 < started:
                    return
                if state['run_id'] != ui.get('runs', {}).get(channel, state['run_id']):
                    return
                # Do not reopen dialogs for historical installations on a later visit.
                if not 0 <= time.time() - state['time'] <= 900:
                    return
            connection.call_method('notify_update_response', [dict(
                message=ui['message'], application=ui['application'],
                proc_id=ui['proc_id'], complete=True)])
        except (OSError, ValueError, KeyError, TypeError):
            pass

    async def component_init(self):
        manager = self.server.lookup_component('update_manager', None)
        if manager is not None:
            helper = manager.cmd_helper
            original = helper.notify_update_response

            def notify(resp, is_complete=False):
                message = resp.decode() if isinstance(resp, bytes) else resp
                app = helper.cur_update_app
                proc = helper.cur_update_id
                channel = app.removeprefix('lugoware_') if app else ''
                match = re.search(r'Git Repo lugoware_(config|system):', message)
                if app == 'full' and match:
                    channel = match.group(1)
                if channel in ('config', 'system'):
                    key = (proc, channel)
                    started = self.requests.setdefault(key, time.time())
                    if not self.ui_pending(proc):
                        self.queue_ui(app, proc, channel, started)
                    # Git success only queues installation. Keep the update dialog open.
                    if is_complete and ('Update Finished' in message or 'Reinstall Complete' in message):
                        self.queue_ui(app, proc, channel, started)
                        original('lugoware_' + channel + ': 다운로드 완료 — 실제 설치 진행 중입니다. 완료 알림을 기다려 주세요.', False)
                        return
                if app == 'full' and is_complete and 'Full Update Complete' in message and self.ui_pending(proc):
                    original('다운로드 완료 — LUGOWARE 실제 설치 및 검증을 기다리는 중입니다.', False)
                    return
                original(resp, is_complete)

            helper.notify_update_response = notify
            for channel in ('config', 'system'):
                updater = getattr(manager, 'updaters', {}).get('lugoware_' + channel)
                if updater is not None:
                    self.enable_retry(updater, channel)
        self.timer.start()

    def failed_install(self, channel):
        try:
            data = json.loads((self.folder / (channel + '-status.json')).read_text())
            return data if data.get('state') == 'failed' else None
        except (OSError, ValueError):
            return None

    def enable_retry(self, updater, channel):
        if getattr(updater, '_lugoware_retry_enabled', False):
            return
        original_status = updater.get_update_status
        original_update = updater.update

        def status():
            data = dict(original_status())
            failed = self.failed_install(channel)
            if failed:
                data['installation_pending'] = True
                data['warnings'] = list(data.get('warnings', [])) + [
                    '설치 실패: 원인을 해결한 뒤 업데이트를 다시 누르세요. 다운로드된 Git 버전은 최신일 수 있습니다.']
                # Mainsail enables Git update buttons from this list. This is an
                # explicitly labelled install task for the real downloaded commit,
                # not a fabricated version or a repository reset.
                if not data.get('commits_behind'):
                    data['commits_behind'] = [dict(
                        sha=data.get('current_hash', ''), author='LUGOWARE installer',
                        date=str(int(failed.get('time', time.time()))),
                        subject='설치 재시도 — 다운로드 완료, 실제 설치 미완료',
                        message=failed.get('detail', ''), tag=None)]
            return data

        async def update():
            await updater.repo.wait_for_refresh()
            if not self.failed_install(channel) or not updater.repo.is_current():
                return await original_update()
            info = original_status()
            if not info.get('is_valid', True) or updater.repo.is_dirty():
                return await original_update()
            updater.notify_status('Retrying failed installation; Git checkout unchanged...')
            await updater.restart_service()
            updater.notify_status('Update Finished...', is_complete=True)
            return True

        updater.get_update_status = status
        updater.update = update
        updater._lugoware_retry_enabled = True

    def ui_pending(self, proc):
        try:
            data = json.loads((self.folder / 'ui-install.json').read_text())
            return data['proc_id'] == proc and not data.get('done')
        except (OSError, ValueError, KeyError):
            return False

    def queue_ui(self, app, proc, channel, started):
        path = self.folder / 'ui-install.json'
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
        if data.get('proc_id') != proc or data.get('done'):
            data = dict(application=app, proc_id=proc, channels={}, done=False)
        data['channels'][channel] = started
        path.write_text(json.dumps(data))

    def stage(self, channel, data):
        if data['state'] != 'running':
            return data['detail']
        path = Path.home() / 'printer_data/logs' / ('lugoware_' + channel + '.log')
        try:
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 32768))
                text = stream.read().decode('utf-8', errors='replace')
            text = text.rsplit('queued:', 1)[-1]
            lines = [line.strip() for line in text.splitlines() if line.startswith(('[', 'Applying latest', 'System and model'))]
            return lines[-1] if lines else data['detail']
        except OSError:
            return data['detail']

    def update_dialog(self, states):
        path = self.folder / 'ui-install.json'
        try:
            ui = json.loads(path.read_text())
            if ui.get('done'):
                return
            manager = self.server.lookup_component('update_manager', None)
            if ui['application'] == 'full' and manager is not None and manager.cmd_helper.is_update_busy():
                return
            current = []
            for channel, started in ui['channels'].items():
                data = states.get(channel)
                # Never treat a prior installation's success as this run's result.
                if not data or int(data['run_id']) / 1e9 < started:
                    return
                current.append((channel, data))
            failed = any(d['state'] == 'failed' for _, d in current)
            done = failed or all(d['state'] == 'complete' for _, d in current)
            message = '\n'.join('lugoware_' + c + ': ' + self.describe(c, d) for c, d in current)
            if message == ui.get('message') and done == ui.get('done'):
                return
            self.server.send_event('update_manager:update_response', dict(
                message=message, application=ui['application'], proc_id=ui['proc_id'], complete=done))
            ui.update(message=message, done=done, runs={c: d['run_id'] for c, d in current})
            path.write_text(json.dumps(ui))
        except (OSError, ValueError, KeyError):
            pass

    def describe(self, channel, data):
        labels = {'queued': '설치 대기 중', 'running': '설치 진행 중',
                  'complete': '업데이트 완료 — 실제 설치 및 검증 완료', 'failed': '설치 실패 — 업데이트 미완료'}
        return labels.get(data['state'], data['state']) + '\n' + self.stage(channel, data)

    async def remove_previous(self, entry_id):
        try:
            await self.announcements.remove_announcement(entry_id)
        except Exception:
            pass

    def poll(self, eventtime):
        states = {}
        for channel in ('config', 'system'):
            path = self.folder / (channel + '-status.json')
            seen = self.folder / (channel + '-announced.txt')
            entry_path = self.folder / (channel + '-announcement-id.txt')
            try:
                data = json.loads(path.read_text())
                states[channel] = data
                description = self.describe(channel, data)
                key = data['run_id'] + ':' + description
                if seen.exists() and seen.read_text() == key:
                    continue
                entry = self.announcements.add_internal_announcement(
                    'lugoware_' + channel + ': ' + description.split('\n')[0],
                    description + '\n상세 로그: ' + data['log'], '',
                    'high' if data['state'] == 'failed' else 'normal', 'lugoware_' + channel)
                if isinstance(entry, dict) and 'entry_id' in entry:
                    if entry_path.exists():
                        self.server.get_event_loop().create_task(self.remove_previous(entry_path.read_text()))
                    entry_path.write_text(entry['entry_id'])
                seen.write_text(key)
            except (OSError, ValueError, KeyError):
                pass
            except Exception:
                logging.exception('LUGOWARE announcement failed; keep polling installation status')
        try:
            self.update_dialog(states)
        except Exception:
            logging.exception('LUGOWARE update dialog delivery failed; retry on next poll')
        signature = tuple((c, d.get('run_id'), d.get('state')) for c, d in sorted(states.items()))
        if signature != getattr(self, '_retry_signature', None):
            self._retry_signature = signature
            manager = self.server.lookup_component('update_manager', None)
            if manager is not None:
                try:
                    manager.cmd_helper.notify_update_refreshed()
                except Exception:
                    self._retry_signature = None
                    logging.exception('LUGOWARE retry-button refresh failed; retry on next poll')
        return eventtime + 2.


def load_component(config):
    return UpdateStatus(config)
