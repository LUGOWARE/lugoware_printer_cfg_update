"""Asynchronous pre-print analysis gate; never sends motion/heater commands."""
import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

def stamp(path):
    p = Path(path).resolve(); s = p.stat()
    return [str(p), s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]

class Preanalysis:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.generation = 0
        self.state = 'idle'; self.progress = 0.; self.error = ''
        self.filename = ''; self.result = None; self.process = None; self.deferred = None
        self.display_start = None
        self.cleanup_running = False
        self.printer.register_event_handler('klippy:ready', self.ready)
        self.printer.register_event_handler('klippy:shutdown', self.cancel)
        self.printer.register_event_handler('klippy:disconnect', self.cancel)
        self.printer.lookup_object('gcode').register_command('LUGO_ANALYSIS_CANCEL', self.cmd_cancel)
        self.printer.lookup_object('gcode').register_command('LUGO_ANALYSIS_CONTINUE', self.cmd_continue)

    def ready(self):
        self.sd = self.printer.lookup_object('virtual_sdcard')
        self.resume = self.sd.do_resume
        self.sd.do_resume = self.start
        self.reactor.register_timer(self.cleanup_tick, self.reactor.monotonic() + 10.)
        for name in ('do_cancel', '_reset_file'):
            original = getattr(self.sd, name)
            def wrapped(*args, _original=original, **kwargs):
                self.cancel()
                return _original(*args, **kwargs)
            setattr(self.sd, name, wrapped)

    def cleanup_tick(self, eventtime):
        if (not self.cleanup_running and not self.printer.is_shutdown()
                and self.state not in ('reading','finishing')
                and self.printer.lookup_object('print_stats').get_status(eventtime)['state']
                    not in ('printing','paused')):
            self.cleanup_running = True
            threading.Thread(target=self.cleanup_work, args=(self.sd.sdcard_dirname,), daemon=True).start()
        return eventtime + 60.

    def cleanup_work(self, root):
        try:
            result = subprocess.run([sys.executable, '-I',
                str(Path(__file__).with_name('cache_cleanup_worker.py')), root],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            if result.returncode == 0 and result.stdout.strip() not in ('','0'):
                logging.info('Removed orphan G-code caches: %s', result.stdout.strip())
        except Exception:
            logging.exception('Idle G-code cache cleanup failed; printing unaffected')
        finally:
            self.cleanup_running = False

    def cancel(self, *args):
        self.generation += 1
        self.state = 'idle'; self.result = None
        self.display_start = None
        deferred = getattr(self, 'deferred', None)
        if deferred is not None and deferred.poll() is None:
            try: deferred.terminate()
            except OSError: pass
        process = self.process
        if process is not None and process.poll() is None:
            try: process.terminate()
            except OSError: pass

    def cmd_cancel(self, gcmd):
        if self.state in ('reading', 'finishing'):
            self.sd._reset_file()

    def cmd_continue(self, gcmd):
        generation = gcmd.get_int('GENERATION')
        if self.state == 'finishing' and generation == self.generation:
            start = self.display_start
            if start is not None: start(self.reactor.monotonic())

    def get_status(self, eventtime):
        return dict(state=self.state, progress=self.progress, filename=self.filename, error=self.error,
                    generation=self.generation)

    def for_file(self, path):
        try:
            if self.result and self.result['stamp'] == stamp(path):
                return self.result
        except OSError: pass
        return None

    def start(self):
        # Paused/recovery streams already have a nonzero file position.
        if self.sd.file_position != 0 or self.sd.current_file is None:
            return self.resume()
        if self.sd.work_timer is not None or self.state in ('reading', 'finishing'):
            raise self.sd.gcode.error('G-code analysis or print already active')
        self.generation += 1; generation = self.generation
        path = self.sd.file_path(); loaded_file = self.sd.current_file
        self.state = 'reading'; self.progress = 0.; self.error = ''
        self.filename = Path(path).name; self.result = None
        threading.Thread(target=self.work, args=(generation, path, loaded_file), daemon=True).start()

    def warm_display(self, generation, path):
        # Optional display-only preparation, after the print gate has opened.
        # Separate process, lower priority and extra pacing; no printer commands.
        try:
            if generation != self.generation: return
            process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).with_name('preanalysis_eta_worker.py')), path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.deferred = process
            if generation != self.generation: process.terminate()
            try: process.wait(timeout=1800)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        except OSError: logging.exception('Optional display analysis unavailable')

    def work(self, generation, path, loaded_file):
        result = None; error = ''
        try:
            process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).with_name('preanalysis_worker.py')), path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.process = process
            if generation != self.generation: process.terminate()
            # Kill hung analysis without blocking the Reactor.
            watchdog = threading.Timer(900, process.kill); watchdog.daemon = True; watchdog.start()
            try:
                for line in process.stdout:
                    item = json.loads(line)
                    if 'progress' in item:
                        value = item['progress']
                        def update(t, value=value):
                            if generation == self.generation: self.progress = value
                        self.reactor.register_async_callback(update)
                    elif 'result' in item: result = item['result']
                stderr = process.stderr.read(4096)
                if process.wait() or result is None: raise ValueError(stderr or 'G-code analysis failed')
                if result['stamp'] != stamp(path): raise ValueError('G-code changed during analysis')
            finally:
                watchdog.cancel(); process.stdout.close(); process.stderr.close()
        except Exception as exc:
            error = str(exc); logging.exception('Pre-print analysis failed')
        def finish(eventtime):
            if generation != self.generation or self.sd.current_file is not loaded_file: return
            self.process = None
            if error:
                self.state = 'error'; self.error = error[:500]; return
            try:
                if result['stamp'] != stamp(path): raise ValueError('G-code changed before start')
                self.result = result; self.progress = 1.; self.state = 'finishing'
                def start(t):
                    if (generation != self.generation or self.state != 'finishing'
                            or self.sd.current_file is not loaded_file):
                        return self.reactor.NEVER
                    self.display_start = None
                    try:
                        if result['stamp'] != stamp(path):
                            raise ValueError('G-code changed before start')
                        self.state = 'ready'
                        self.resume()
                        threading.Thread(target=self.warm_display, args=(generation, path), daemon=True).start()
                    except Exception as exc:
                        self.state = 'error'; self.error = str(exc)
                    return self.reactor.NEVER
                self.display_start = start
                # Headless/Mainsail prints must still start if no screen can ACK.
                # No blocking sleep or G-code mutex held during display completion.
                def fallback(t):
                    if generation == self.generation and self.state == 'finishing':
                        logging.info('Preanalysis display ACK unavailable; starting after 5s fallback')
                    return start(t)
                self.reactor.register_timer(fallback, eventtime + 5.)
            except Exception as exc:
                self.state = 'error'; self.error = str(exc)
        self.reactor.register_async_callback(finish)

def load_config(config): return Preanalysis(config)

