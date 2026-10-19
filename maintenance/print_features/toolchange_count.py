"""Count the explicit tool selections used by the LUGOWARE print macros."""
import re


def count_toolchanges(lines):
    current = None
    total = 0
    for line in lines:
        code = line.split(';', 1)[0].strip()
        if not code:
            continue
        command = code.split()[0].upper()
        target = None
        if command == 'START_PRINT':
            match = re.search(r'\bINITIAL_TOOL=(\d+)\b', code, re.I)
            target = int(match.group(1)) if match else 0
        elif command == 'CHANGE_TOOL':
            match = re.search(r'\bNEXT_TOOL=(\d+)\b', code, re.I)
            if match:
                target = int(match.group(1))
        elif re.fullmatch(r'T\d+', command):
            target = int(command[1:])
        if target is not None and target != current:
            total += 1
            current = target
    return total
