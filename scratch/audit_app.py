with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

checks = [
    '00e5ff', 'rgba(0,', 'rgba(15,', 'rgba(30,', 'linear-gradient',
    '#fff', '#000', 'accent-cyan', 'accent-amber', 'accent-emerald'
]

for idx, line in enumerate(lines, 1):
    for c in checks:
        if c in line:
            print(f"L{idx} [{c}]: {line.strip()}")
            break

