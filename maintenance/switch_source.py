"""Switch official M5P checkouts without merging the two distribution histories."""
import os
from pathlib import Path
import subprocess
import sys

URLS = tuple('https://' + host + '/LUGOWARE/lugoware_printer_cfg_update.git'
             for host in ('github.com', 'gitee.com'))


def read(git, *args):
    return subprocess.check_output(git + list(args), text=True).strip()


def switch(home, backup, model, target):
    if target not in URLS or model not in ('FLEX4_M', 'FLEX4_L', 'FLEX4_W'):
        raise ValueError('Unexpected release target or printer model')
    plans = []
    for name, branch in (('lugoware_config', model), ('lugoware_system', 'main')):
        repo = home / name
        if not repo.exists():
            continue
        git = ['git', '-C', str(repo)]


        origin = read(git, 'config', '--get', 'remote.origin.url')
        if not origin.endswith('.git'):
            origin += '.git'
        if origin not in URLS:
            raise RuntimeError('Unknown origin: ' + name)
        plans.append((repo, branch, origin))
    if all(origin == target for _, _, origin in plans):
        return
    backup.mkdir(parents=True, exist_ok=False)
    changes = []
    for repo, branch, origin in plans:
        git = ['git', '-C', str(repo)]
        if (repo.is_symlink() or not (repo / '.git').is_dir()
                or read(git, 'branch', '--show-current') != branch or read(git, 'status', '--porcelain')
                or subprocess.run(git + ['merge-base', '--is-ancestor', 'HEAD',
                                         'refs/remotes/origin/' + branch]).returncode):
            raise RuntimeError('Inspect local edits, commits or model before switching: ' + repo.name)
        if origin != target:
            staged = backup / (repo.name + '-incoming')
            subprocess.run(['git', 'clone', '--single-branch', '--branch', branch,
                            '--no-tags', target, str(staged)], check=True)
            changes.append((repo, staged, backup / repo.name))
    moved = []
    try:
        for repo, staged, original in changes:
            repo.rename(original)
            moved.append((repo, staged, original))
            staged.rename(repo)
    except OSError:
        for repo, staged, original in reversed(moved):
            if repo.exists():
                repo.rename(staged)
            original.rename(repo)
        raise
    print('Update source switched to', target, 'Previous checkouts:', backup, flush=True)


if __name__ == '__main__':
    switch(Path.home(), Path(os.environ['BACKUP_DIR']) / 'previous-source',
           sys.argv[1], sys.argv[2])
