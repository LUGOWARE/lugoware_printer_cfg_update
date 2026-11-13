"""Bounded, nonblocking timing telemetry. No printer objects in log thread."""
from functools import wraps
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import threading
import time

_queue = queue.Queue(maxsize=128)
_local = threading.local()
_started = False

def start():
    global _started
    if _started:return
    _started=True
    threading.Thread(target=_write,daemon=True,name='recovery-latency').start()

def _write():
    try:
        path=Path.home()/'printer_data/logs/lugo_latency.log'
        path.parent.mkdir(parents=True,exist_ok=True)
        handler=RotatingFileHandler(str(path),maxBytes=1048576,backupCount=2)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        while True:
            item=_queue.get()
            handler.emit(logging.LogRecord('recovery-latency',logging.INFO,'',0,json.dumps(item),(),None))
    except Exception:
        logging.exception('Recovery timing log unavailable (printing unaffected)')

def begin():return time.monotonic(),time.thread_time()

def end(name,started):
    # Thread-local aggregation; no disk I/O, logging lock or blocking put here.
    now=time.monotonic();wall=now-started[0];cpu=time.thread_time()-started[1]
    stats=getattr(_local,'stats',None)
    if stats is None:stats={};_local.stats=stats
    row=stats.setdefault(name,{'count':0,'wall_max_ms':0.,'cpu_max_ms':0.,'next':0.})
    row['count']+=1;row['wall_max_ms']=max(row['wall_max_ms'],wall*1000);row['cpu_max_ms']=max(row['cpu_max_ms'],cpu*1000)
    if now<row['next']:return
    item={'scope':name,'mono':now,'start_mono':started[0],'wall_ms':wall*1000,'cpu_ms':cpu*1000,
          'count':row['count'],'wall_max_ms':row['wall_max_ms'],'cpu_max_ms':row['cpu_max_ms']}
    row.update(count=0,wall_max_ms=0.,cpu_max_ms=0.,next=now+5.)
    try:_queue.put_nowait(item)
    except queue.Full:pass  # Drop diagnostics, never delay motion.

def timed(name):
    def decorate(fn):
        @wraps(fn)
        def call(*args,**kwargs):
            started=begin()
            try:return fn(*args,**kwargs)
            finally:end(name,started)
        return call
    return decorate
