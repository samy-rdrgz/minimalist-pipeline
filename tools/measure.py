"""Measure the addon's package as `blender --command extension build` makes it:
the files git tracks, the manifest's exclusions, their zip and Python lines.

    python3 tools/measure.py .
"""
import fnmatch, io, os, subprocess, sys, tomllib, zipfile, ast, tokenize
repo = sys.argv[1]
os.chdir(repo)
files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
man = tomllib.load(open("blender_manifest.toml", "rb"))
pats = man["build"]["paths_exclude_pattern"]
def excluded(p):
    parts = p.split("/")
    for pat in pats:
        if pat.endswith("/"):
            d = pat.strip("/")
            if pat.startswith("/"):
                if parts[0] == d: return True
            elif d in parts[:-1]: return True
        elif pat.startswith("/"):
            if "/" not in p and fnmatch.fnmatch(p, pat[1:]): return True
        else:
            if any(fnmatch.fnmatch(x, pat) for x in parts): return True
    return False
keep = [f for f in files if not excluded(f) and os.path.exists(f)]
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for f in keep: z.write(f, f)
raw = sum(os.path.getsize(f) for f in keep)
py = [f for f in keep if f.endswith(".py")]
def code_lines(f):
    src = open(f, encoding="utf-8").read()
    lines = set()
    try:
        tree = ast.parse(src)
        doc = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str):
                doc.update(range(n.body[0].lineno, n.body[0].end_lineno + 1))
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER): continue
            for l in range(tok.start[0], tok.end[0] + 1):
                if l not in doc: lines.add(l)
    except SyntaxError: return 0
    return len(lines)
tot = sum(sum(1 for _ in open(f, encoding="utf-8")) for f in py)
code = sum(code_lines(f) for f in py)
other = {}
for f in keep:
    ext = os.path.splitext(f)[1] or f
    other[ext] = other.get(ext, 0) + os.path.getsize(f)
print(f"files={len(keep)} raw={raw/1024:.0f}KB zip={len(buf.getvalue())/1024:.0f}KB py_lines={tot} py_code_lines={code}")
print("by ext:", {k: f"{v/1024:.0f}KB" for k, v in sorted(other.items(), key=lambda x: -x[1])})
