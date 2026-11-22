import os, json, subprocess

p = r'C:\Users\SIGMA\.gemini\antigravity\daemon'
if os.path.exists(p):
    files = os.listdir(p)
    alive = 0
    stale = []

    # Get list of running PIDs via tasklist
    tasklist = subprocess.check_output(['tasklist', '/FO', 'CSV']).decode('utf-8', errors='ignore')
    running_pids = set()
    for line in tasklist.splitlines()[1:]:
        parts = line.split('","')
        if len(parts) > 1:
            pid_str = parts[1].replace('"', '')
            if pid_str.isdigit():
                running_pids.add(int(pid_str))

    for f in files:
        fp = os.path.join(p, f)
        try:
            with open(fp, 'r') as jf:
                d = json.load(jf)
                pid = d.get('pid')
                if pid in running_pids:
                    alive += 1
                else:
                    stale.append(fp)
        except Exception:
            stale.append(fp)

    print(f'Alive hubs: {alive}, Stale hubs: {len(stale)}')
    for s in stale:
        try:
            os.remove(s)
        except Exception as e:
            print(f'Error removing {s}: {e}')
    print(f'Cleaned up {len(stale)} dead daemon socket files!')
