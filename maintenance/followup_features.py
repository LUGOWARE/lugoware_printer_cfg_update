"""November follow-up migrations. Preserve board motion settings."""
import json,re
from pathlib import Path

def ui(text,name,reverse=False):
    pairs=json.loads(Path(__file__).with_name('print_features').joinpath('followup_ui.json').read_text(encoding='utf-8')).get(name,[])
    for old,new in (reversed(pairs) if reverse else pairs):
        if reverse:
            if new in text:
                if text.count(new)!=1:raise ValueError('Ambiguous follow-up UI: '+name)
                text=text.replace(new,old,1)
        elif new not in text:
            if text.count(old)!=1:raise ValueError('Unsupported follow-up UI: '+name+' '+old[:100])
            text=text.replace(old,new,1)
    return text

def first_tool(text):
    match=re.search(r'(?ms)^\[gcode_macro START_PRINT\][^\n]*\n.*?(?=^\[|\Z)',text)
    if not match:raise ValueError('Missing START_PRINT')
    block=match[0]
    if re.search(r'^\s*EXCLUDE_TOOL_PREPARE\b',block,re.M):return text
    change=re.search(r'(?m)^([ \t]*)CHANGE_TOOL (.+)$',block)
    if not change:raise ValueError('Missing first CHANGE_TOOL')
    approach=list(re.finditer(r'(?m)^[ \t]*G[01] X([-+\d.]+) F([\d.]+)[ \t]*(?:;[^\n]*)?$',block[:change.start()]))
    if not approach:raise ValueError('Missing first tool approach move')
    move=approach[-1]
    replacement=change[1]+'EXCLUDE_TOOL_PREPARE '+change[2]+' APPROACH_X='+move[1]+' APPROACH_F='+move[2]
    block=block[:change.start()]+replacement+block[change.end():]
    block=block[:move.start()]+block[move.end():]
    # Material-dependent heating belongs to the selected remaining tool.
    pattern=r'(?m)^[ \t]*M104 S\{target_EXTRUDER\}[ \t]*\n[ \t]*TEMPERATURE_WAIT SENSOR=extruder MINIMUM=\{target_EXTRUDER - 5\} MAXIMUM=\{target_EXTRUDER \+ 20\}[ \t]*$'
    block,count=re.subn(pattern,'    # First material temperature is resolved by EXCLUDE_TOOL_PREPARE.',block)
    if count!=1:raise ValueError('Unsupported first material heat wait')
    return text[:match.start()]+block+text[match.end():]
