"""Patch only update-dialog methods; retain device-specific base-panel changes."""
import ast
import json
from pathlib import Path

OLD = '''            if "message" in data:
                self.labels["update_progress"].set_text(
                    f"{self.labels['update_progress'].get_text().strip()}\\n{data['message']}\\n"
                )
            if "complete" in data and data["complete"]:'''
NEW = '''            logging.info("Update progress: %s", data.get("message", ""))
            terminal = self.render_update_progress(data)
            if terminal:'''

def patch(source, assets=None):
    assets=Path(assets) if assets else Path(__file__).with_name('recovery')
    snippets=json.loads((assets/'progress_ui.json').read_text(encoding='utf-8'))
    tree=ast.parse(source)
    classes=[node for node in tree.body if isinstance(node,ast.ClassDef) and
             any(isinstance(m,ast.FunctionDef) and m.name=='show_update_dialog' for m in node.body)]
    if len(classes)!=1:raise ValueError('Unsupported base-panel update dialog')
    methods={node.name:node for node in classes[0].body if isinstance(node,ast.FunctionDef)}
    if 'finish_updating' not in methods:raise ValueError('Missing update completion handler')
    lines=source.splitlines(True)
    replacements=[]
    missing=[]
    for name,snippet in snippets.items():
        snippet=snippet.rstrip()+"\n"
        if name in methods:
            node=methods[name];replacements.append((node.lineno-1,node.end_lineno,snippet))
        else:missing.append(snippet)
    for start,end,text in sorted(replacements,reverse=True):
        lines[start:end]=[text]
    result=''.join(lines)
    if missing:
        marker='    def finish_updating('
        result=result.replace(marker,'\n'.join(missing)+'\n'+marker,1)
    if NEW not in result:
        if result.count(OLD)!=1:raise ValueError('Unsupported update notification handler')
        result=result.replace(OLD,NEW,1)
    for imp in ('from ks_includes.lugoware_update_progress import Progress',
                'from ks_includes.update_progress_i18n import caption as update_progress_caption'):
        if imp not in result:result=imp+'\n'+result
    compile(result,'base_panel.py','exec')
    return result
