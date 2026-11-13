"""Optional display ETA warmup: isolated, paced, safe to discard on cancel."""
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path.home()/'KlipperScreen/ks_includes'))
import exclusion_eta

if __name__ == '__main__':
    if hasattr(os, 'nice'): os.nice(19)
    # Existing analyzer yields every 2048 lines. Use an independent time proxy
    # to increase pacing without altering global time.sleep or other modules.
    class PacedTime:
        @staticmethod
        def sleep(seconds): time.sleep(max(seconds, .10))
    exclusion_eta.time = PacedTime
    exclusion_eta.index_file(sys.argv[1])
