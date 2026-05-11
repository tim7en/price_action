import sys
io_enc = "utf-8"
sys.stdout.reconfigure(encoding=io_enc)

with open("src/price_action/sector_rotation_report.py", encoding="utf-8") as f:
    src = f.read()
lines = src.splitlines()
fstring_lines = lines[4659:4932]
raw = "\n".join(fstring_lines)
cleaned = raw.replace("{{", "\x01").replace("}}", "\x02")

i = 0
exprs = []
while i < len(cleaned):
    if cleaned[i] == "{":
        depth = 1
        j = i + 1
        while j < len(cleaned) and depth > 0:
            if cleaned[j] == "{":
                depth += 1
            elif cleaned[j] == "}":
                depth -= 1
            j += 1
        expr = cleaned[i + 1 : j - 1]
        exprs.append(expr)
        i = j
    else:
        i += 1

backslash = chr(92)
for idx, e in enumerate(exprs):
    if backslash in e:
        snippet = e[:200]
        print(f"#{idx}: {snippet!r}")
print("total expressions:", len(exprs))
