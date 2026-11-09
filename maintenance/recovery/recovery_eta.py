"""Bounded recovery-only estimate from slicer M73 remaining-time anchors."""
import bisect


def remaining_at(timeline, position):
    if not timeline: return None
    i = bisect.bisect_right([p['offset'] for p in timeline], position) - 1
    if i < 0: return float(timeline[0]['remaining'])
    left = timeline[i]
    if i + 1 == len(timeline): return float(left['remaining'])
    right = timeline[i+1]
    fraction = (position-left['offset']) / max(1, right['offset']-left['offset'])
    return max(0., left['remaining'] + fraction*(right['remaining']-left['remaining']))


def estimate(context, stats, position):
    if (not context or stats.get('filename') != context['filename']
            or stats.get('state') not in ('printing','paused')):
        return None
    elapsed = max(0., stats.get('print_duration', 0.))
    initial = context['initial_remaining']
    remaining = remaining_at(context['timeline'], position)
    if initial is None or remaining is None:
        return {'active':True,'filename':context['filename'],'remaining':None,'elapsed':elapsed}
    consumed = max(0., initial-remaining)
    # Do not extrapolate from tiny startup progress or from reset filament use.
    weight = min(1., max(0., (elapsed-120.)/480.)) if consumed >= 60. else 0.
    scale = max(.5, min(2., elapsed/consumed)) if consumed else 1.
    remaining *= (1.-weight) + weight*scale
    return {'active':True,'filename':context['filename'],'remaining':max(0.,remaining),
            'elapsed':elapsed,'initial_remaining':initial,'source':'slicer_M73_recovery'}
