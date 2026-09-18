"""Permit a completed DFU transfer to proceed to mandatory live verification."""
import re
import subprocess
import sys


def completed_with_reset_error(output):
    done = output.find('File downloaded successfully')
    if done < 0 or 'Download done.' not in output[:done]:
        return False
    errors = re.findall(r'^dfu-util: (.*)$', output, re.MULTILINE)
    failures = [line for line in errors if line not in (
        'Invalid DFU suffix signature',
        'A valid DFU suffix will be required in a future dfu-util release!!!')]
    return (len(failures) == 1
            and failures[0].startswith('Error during download get_status')
            and output.find('dfu-util: Error during download get_status') > done)


def main():
    result = subprocess.run(sys.argv[1:], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    print(result.stdout, end='', flush=True)
    if result.returncode and not completed_with_reset_error(result.stdout):
        raise SystemExit(result.returncode)
    if result.returncode:
        print('DFU transfer completed; runtime verification is required.')


if __name__ == '__main__':
    main()
