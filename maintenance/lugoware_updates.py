"""Publish durable updater results as Mainsail announcements, including after restart."""
import json
from pathlib import Path


class UpdateStatus:
    def __init__(self, config):
        self.server = config.get_server()
        self.announcements = self.server.load_component(config, 'announcements')
        self.folder = Path.home() / '.local/share/lugoware'
        self.timer = self.server.get_event_loop().register_timer(self.poll)

    async def component_init(self):
        self.timer.start()

    def poll(self, eventtime):
        for channel in ('config', 'system'):
            path = self.folder / (channel + '-status.json')
            seen = self.folder / (channel + '-announced.txt')
            try:
                data = json.loads(path.read_text())
                key = data['run_id'] + ':' + data['state']
                if seen.exists() and seen.read_text() == key:
                    continue
                self.announcements.add_internal_announcement(
                    'lugoware_' + channel + ': ' + data['state'],
                    data['detail'] + '\nLog: ' + data['log'], '',
                    'high' if data['state'] == 'failed' else 'normal', 'lugoware_' + channel)
                seen.write_text(key)
            except (OSError, ValueError, KeyError):
                pass
        return eventtime + 2.


def load_component(config):
    return UpdateStatus(config)
