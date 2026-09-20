import re

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

dark_patterns = [
    r'#0f172a', r'#1e293b', r'#334155', r'#111827', r'#1f2937', r'#000',
    r'rgba\(', r'rgb\(', r'var\(--accent', r'linear-gradient'
]

print("Scanning for dark / colored styles in JSX/CSS/JS:")
for idx, line in enumerate(lines, 1):
    # Only check inside the HTML / React portion (from line 100 onwards)
    if idx < 100:
        continue
    for p in dark_patterns:
        if re.search(p, line):
            print(f"L{idx}: {line.strip()[:100]}")
            break

