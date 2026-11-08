"""Reapply the local Markdown extension after regenerating the Archify HTML."""
from pathlib import Path
import re

folder = Path(__file__).resolve().parent
page = folder / "wxbot.html"
html = page.read_text(encoding="utf-8")
backup = folder / "wxbot.before-node-notes.html"
if not backup.exists():
    backup.write_bytes(page.read_bytes())
html = re.sub(r'<!-- wxbot-node-notes:start -->.*?<!-- wxbot-node-notes:end -->\n?', '', html, flags=re.S)
html = re.sub(r'\s*<button id="btn-node-note"[^>]*>.*?</button>', '', html, flags=re.S)
anchor = '            <button id="btn-focus-relations"'
if anchor not in html:
    raise SystemExit("Archify node details changed; inspect the insertion point before applying.")
button = ('            <button id="btn-node-note" type="button" title="打开节点 Markdown 文档" '
          'aria-label="打开节点文档" aria-haspopup="dialog" aria-controls="node-note" hidden>文档</button>\n')
html = html.replace(anchor, button + anchor, 1)
extension = (folder / "node-notes.extension.html").read_text(encoding="utf-8")
html = html.replace('</body>', extension + '</body>', 1)
page.write_text(html, encoding="utf-8")
print("Updated", page)
