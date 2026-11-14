"""Duplicate code: windows of N code lines, normalized (names -> N, strings
-> S, numbers -> 0, no comments nor docstrings), found in several places.

    python3 tools/dupes.py . 8
"""
import io, sys, tokenize, keyword, glob, os, ast
from collections import defaultdict
root, N = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8
KEEP = set(keyword.kwlist) | {"self", "True", "False", "None"}
def norm_lines(path):
    src = open(path, encoding="utf-8").read()
    try: tree = ast.parse(src)
    except SyntaxError: return []
    doc = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str):
            doc.update(range(n.body[0].lineno, n.body[0].end_lineno + 1))
    lines = defaultdict(list)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER): continue
        if tok.start[0] in doc: continue
        if tok.type == tokenize.NAME: t = tok.string if tok.string in KEEP else "N"
        elif tok.type == tokenize.STRING or tok.type == getattr(tokenize, "FSTRING_START", -1): t = "S"
        elif tok.type in (getattr(tokenize, "FSTRING_MIDDLE", -2), getattr(tokenize, "FSTRING_END", -3)): continue
        elif tok.type == tokenize.NUMBER: t = "0"
        else: t = tok.string
        lines[tok.start[0]].append(t)
    out = [(ln, " ".join(ts)) for ln, ts in sorted(lines.items())]
    return [(ln, s) for ln, s in out if s not in (")", "]", "}", "),", "],", "},", "else :", "try :", "N ,", "S ,")]
seen = defaultdict(list)
for f in glob.glob(os.path.join(root, "**/*.py"), recursive=True):
    rel = os.path.relpath(f, root)
    if rel.startswith(("docs", "templates")) or "/." in rel: continue
    L = norm_lines(f)
    for i in range(len(L) - N + 1):
        key = "\n".join(s for _, s in L[i:i + N])
        if len(key) < 25 * N // 2: continue  # trivially short windows
        seen[key].append((rel, L[i][0]))
groups = []
for key, locs in seen.items():
    files = {}
    for rel, ln in locs: files.setdefault((rel, ln // 1), ln)
    if len(locs) > 1: groups.append((len(locs), locs))
# merge overlapping windows: keep first window of each run
reported = set(); res = []
for cnt, locs in sorted(groups, key=lambda g: -g[0]):
    sig = tuple(sorted((r, l // 6) for r, l in locs))
    if sig in reported: continue
    reported.add(sig); res.append(locs)
# collapse consecutive windows into regions
regions = defaultdict(set)
for locs in res:
    regions[tuple(sorted(r for r, _ in locs))].add(tuple(sorted(locs)))
print(f"{len(res)} duplicated windows of {N} lines")
pairs = defaultdict(int)
for locs in res:
    pairs[" | ".join(sorted(f"{r}:{l}" for r, l in locs[:4]))] += 1
import itertools
shown = 0
for locs in sorted(res, key=lambda l: (l[0][0], l[0][1])):
    print("  ", ", ".join(f"{r}:{l}" for r, l in locs[:5]))
    shown += 1
    if shown > 80: break
