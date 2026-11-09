import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'maintenance/recovery'))
from lugoware_release_notes import parse_notes, read_notes

def payload(text, version='1.0'):
    return json.dumps({'schema':1,'lugoware_system':{'version':version,'date':'2026-11-09',
        'notes':{'ko':[text],'en':['English note']}}}).encode()

class NotesTests(unittest.TestCase):
    def test_languages_and_plain_text(self):
        result=parse_notes(payload('<b>설명</b>'),'lugoware_system','ko')
        self.assertIn('• <b>설명</b>',result['body'])
        self.assertIn('English note',parse_notes(payload('설명'),'lugoware_system','fr')['body'])

    def test_missing_invalid_and_oversized_are_empty(self):
        for raw in (b'bad',b'[]',b'{}',b'x'*65537,b'{"schema":1,"lugoware_system":null}'):
            self.assertIsNone(parse_notes(raw,'lugoware_system','ko'))
        self.assertIsNone(read_notes('.', '../config','HEAD','ko'))

    def test_exact_revisions_not_working_tree_or_commit_message(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory)/'lugoware_system';repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL).decode().strip()
            git('init');git('config','user.name','Test');git('config','user.email','test@example.invalid')
            path=repo/'release_notes.json';path.write_bytes(payload('이전 설명'))
            git('add','.');git('commit','-m','INTERNAL ONLY');old=git('rev-parse','HEAD')
            path.write_bytes(payload('새 설명','2.0'));git('add','.');git('commit','-m','INTERNAL TWO')
            new=git('rev-parse','HEAD');path.write_bytes(payload('아직 게시하지 않은 설명','3.0'))
            self.assertIn('이전 설명',read_notes(directory,'lugoware_system',old,'ko')['body'])
            result=read_notes(directory,'lugoware_system',new,'ko')
            self.assertEqual(result['version'],'2.0')
            self.assertIn('새 설명',result['body']);self.assertNotIn('INTERNAL',result['body'])
            self.assertIsNone(read_notes(directory,'lugoware_system','0'*40,'ko'))

if __name__=='__main__':unittest.main()
