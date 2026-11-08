"""Validate document links and the canonical Archify node-document catalog."""
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

spec = importlib.util.spec_from_file_location("document_migration", Path(__file__).with_name("migrate.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
applied = "--applied" in sys.argv
if not any(mod.STAGED.glob('*.md')):
    applied = True
folder = mod.ROOT / "architecture-notes" if applied else mod.STAGED
manifest = json.loads((mod.WORK / "manifest.json").read_text("utf-8"))
deleted = {s["path"] for s in manifest["sources"]}
issues = []
links = 0
for file in folder.glob("*.md"):
    def validate_line(line):
        global links
        line = re.sub(r"`+[^`]*`+", "", line)
        for match in re.finditer(r"(?<!!)\[([^\]\n]+)\]\((<[^>\n]+>|[^)\n]+)\)", line):
            value = match[2].strip().strip("<>")
            if urlsplit(value).scheme or value.startswith("/"): continue
            target, _, anchor = value.partition("#")
            if not target:
                if anchor.startswith("doc-") and f'id="{anchor}"' not in file.read_text("utf-8"):
                    issues.append(f"{file.name}: missing local anchor {anchor}")
                continue
            target = unquote(target)
            physical = (mod.ROOT / "architecture-notes" / target).resolve()
            if not physical.is_relative_to(mod.ROOT): continue
            relative = physical.relative_to(mod.ROOT).as_posix()
            staged = folder / physical.name if physical.parent == mod.ROOT / "architecture-notes" else physical
            if relative in deleted:
                issues.append(f"{file.name}: link to deleted source {value}")
            elif not staged.exists():
                issues.append(f"{file.name}: missing file {value}")
            elif anchor.startswith("doc-") and f'id="{anchor}"' not in staged.read_text("utf-8"):
                issues.append(f"{file.name}: missing anchor {value}")
            links += 1
        return line
    mod.outside_fences(file.read_text("utf-8"), validate_line)
catalog = json.loads((mod.ROOT / "architecture-notes/index.json").read_text("utf-8"))
bound = {Path(note["file"]).stem for note in catalog["nodes"]}
diagram = (mod.ROOT / catalog["diagram"]).read_text("utf-8")
node_ids = set(re.findall(r'data-node-id="([\w-]+)"', diagram))
for note in catalog["nodes"]:
    owners = note.get("diagram_nodes", [])
    if not owners or not set(owners) <= node_ids:
        issues.append(f'Invalid Archify owner for {note["file"]}: {owners}')
extension = (mod.ROOT / ".archify/architecture-wxbot-20261107-201947/node-notes.extension.html").read_text("utf-8")
mapping = re.search(r"const nodeNotes = Object.freeze\(\{(.*?)\}\);", extension, re.S)[1]
direct = set(re.findall(r':\s*"([\w-]+)"', mapping))
if not direct <= bound: issues.append(f"Direct document mappings missing from catalog: {direct - bound}")
actual = {p.stem for p in folder.glob("*.md")}
if bound != actual: issues.append(f"Node bindings differ: missing={bound - actual}, unbound={actual - bound}")
print(json.dumps({"links": links, "bound_documents": len(bound), "issues": sorted(set(issues))}, ensure_ascii=False, indent=2))
raise SystemExit(bool(issues))
