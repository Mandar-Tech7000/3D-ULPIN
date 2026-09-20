with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for idx, line in enumerate(lines, 1):
    if '\\n' in line:
        stripped = line.strip()
        if not ('text:' in stripped or 'alert(' in stripped or '`' in stripped):
            print(f"L{idx}: {stripped}")

