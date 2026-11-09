"""Checkpoint-only exclusion state, restored after SD reset and before resume."""
import copy
import math

FIELDS=('last_position','last_position_extruded','last_position_excluded',
        'max_position_extruded','max_position_excluded','extruder_adj',
        'initial_extrusion_moves','in_excluded_region','extrusion_offsets')
GUARD=('pending','pending_temp','upcoming','skipped','replayed','filtered_wipe_gaps',
       'startup_excludes','first_object','first_tool')

def capture(printer):
    ex=printer.lookup_object('exclude_object',None)
    guard=printer.lookup_object('exclude_tool_guard',None)
    return {'version':1,'transform':bool(ex and ex.next_transform),
            'exclude':{k:copy.deepcopy(getattr(ex,k)) for k in FIELDS} if ex and ex.next_transform else {},
            'guard':{k:copy.deepcopy(getattr(guard,k)) for k in GUARD} if guard else {}}

def validate(snap):
    excluded=snap.get('exclude_object',{}).get('excluded_objects',[])
    deferred=snap.get('exclude_tool_guard',{}).get('deferred_toolchange')
    state=snap.get('exclusion_internal',{})
    if not (excluded or deferred):return ''
    if state.get('version')!=1 or (excluded and not state.get('transform')):
        return 'This older record has no restorable excluded-object state.'
    if state.get('transform') and any(k not in state.get('exclude',{}) for k in FIELDS):
        return 'Incomplete excluded-object coordinate state.'
    if deferred and not state.get('guard',{}).get('pending'):
        return 'Incomplete deferred tool change state.'
    return ''

def restore(printer,snap):
    state=snap.get('exclusion_internal')
    if not state:return
    ex=printer.lookup_object('exclude_object',None)
    if state.get('transform'):
        ex._register_transform()
        for k,v in state['exclude'].items():
            if k in FIELDS:setattr(ex,k,copy.deepcopy(v))
        # Docking/priming changed the physical E origin. Keep saved virtual E.
        current=printer.lookup_object('toolhead').get_position()[3]
        delta=snap['toolhead']['position'][3]-current
        for offset in ex.extrusion_offsets.values():offset[3]+=delta
    guard=printer.lookup_object('exclude_tool_guard',None)
    if guard:
        for k,v in state.get('guard',{}).items():
            if k in GUARD:setattr(guard,k,copy.deepcopy(v))
        guard.startup_active=False
