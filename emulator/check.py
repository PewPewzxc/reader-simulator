"""Boot every firmware in emulator/candidates.json in eink-qemu (headless) and write web/site/emulator.json with
the ones that reach a steady screen. Each run: boot, screenshot, press Down, screenshot (about 15 s per firmware).
  python -I emulator/check.py <eink-qemu.exe> <work dir> [--files DIR] [--only NAME]
--files: a folder with .bin files that are not downloadable yet (found by file name before downloading).
--only: test only the firmwares whose name contains NAME and keep the other entries of the current emulator.json.
<work dir>/sheet.html shows every screenshot."""
import hashlib, html, json, os, re, shutil, subprocess, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'web', 'site', 'emulator.json')
MACHINE = {'X3': 'x3', 'X4 Classic': 'x4', 'X4 Pro': 'x4pro'}
FRAME = {'X3': 'x3', 'X4 Classic': 'x4-classic', 'X4 Pro': 'x4-pro'}
CHIP = {5: ['X3', 'X4 Classic'], 9: ['X4 Pro']}  # ESP image header chip id: 5 = ESP32-C3, 9 = ESP32-S3


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def fetch(url, dest):
    if not os.path.exists(dest):
        req = urllib.request.Request(url, headers={'User-Agent': 'reader-simulator-emulator-check'})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest + '.part', 'wb') as f:
            f.write(r.read())
        os.replace(dest + '.part', dest)
    return dest


def boot(eq, fw, model, run_dir, power_hold):
    """Returns (booted, keys work, error). Booted = `ready` passed with a picture that is not blank.
    A finished run in run_dir is read again instead of repeated: delete the folder to test again."""
    log = os.path.join(run_dir, 'run.jsonl')
    if os.path.exists(log) and '"type":"end"' in open(log, encoding='utf-8').read():
        return result(open(log, encoding='utf-8').read(), run_dir)
    shutil.rmtree(run_dir, ignore_errors=True)
    cmd = [eq, 'run', fw, '--machine', MACHINE[model], '--turbo', '--ready-timeout', '120', '--timeout', '20', '--out', run_dir]
    if power_hold:
        cmd += ['--power-hold', str(power_hold)]
    cmd += ['ready', 'shot:boot', 'press:down', 'wait-screen', 'shot:down']
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=300).stdout
    except subprocess.TimeoutExpired:
        return False, False, 'timed out'
    return result(out, run_dir)


def result(out, run_dir):
    steps = [json.loads(l) for l in out.splitlines() if l.startswith('{')]
    ok = {s.get('text'): s.get('ok') for s in steps if s.get('type') == 'step'}
    end = next((s for s in steps if s.get('error') and s.get('type') != 'step'), {})
    shots = {s.get('text'): s.get('pixels_sha256') for s in steps if s.get('step') == 'shot'}
    booted = bool(ok.get('ready') and shots.get('shot:boot'))
    if booted:  # a blank screen is not a boot; it compresses to a tiny PNG
        booted = os.path.getsize(os.path.join(run_dir, 'shots', 'boot.png')) > 2000
    keys = booted and bool(shots.get('shot:down')) and shots.get('shot:down') != shots.get('shot:boot')
    return booted, keys, end.get('error')


def main():
    args = sys.argv[1:]
    opt = lambda k: args[args.index(k) + 1] if k in args else None
    eq, work = args[0], args[1]
    files, only = opt('--files'), opt('--only')
    os.makedirs(os.path.join(work, 'bins'), exist_ok=True)
    cands = json.load(open(os.path.join(HERE, 'candidates.json'), encoding='utf-8'))['firmwares']
    keep = []
    if only and os.path.exists(OUT):
        keep = [b for b in json.load(open(OUT, encoding='utf-8'))['builds'] if only.lower() not in b['name'].lower()]
    found, sheet = [], []
    for c in cands:
        if only and only.lower() not in c['name'].lower():
            continue
        owner, repo, tag = (c.get('release') or c['repo'] + '/' + c['tag'] + '/').split('/')[:3]  # unused for full URLs
        for asset, models in c['bins'].items():
            url = asset if asset.startswith('https:') else \
                f'https://github.com/{owner}/{repo}/releases/download/{urllib.parse.quote(tag, safe="")}/{asset}'
            local = os.path.join(files, asset) if files and not asset.startswith('https:') else None
            name = slug(c['repo'] + '-' + c['tag'] + '-' + (asset if not asset.startswith('https:') else asset.rsplit('=', 2)[-2]))
            try:
                path = local if local and os.path.exists(local) else fetch(url, os.path.join(work, 'bins', name + '.bin'))
            except Exception as e:
                print(f'{c["name"]} {asset}: download failed: {e}')
                continue
            with open(path, 'rb') as f:
                head = f.read(16)
            chip = int.from_bytes(head[12:14], 'little') if head[:1] == b'\xe9' else None
            for model in [m for m in models or CHIP.get(chip, []) if chip not in CHIP or m in CHIP[chip]]:
                bid = slug(f'{c["repo"]}-{c["tag"]}-{model}')
                if models is None and len(c['bins']) > 1:
                    bid = slug(f'{name}-{model}')  # several plain .bins for the same reader (CrossPDF tiny / xlarge)
                run_dir = os.path.join(work, 'runs', bid)
                hold = c.get('power_hold')
                booted, keys, err = boot(eq, path, model, run_dir, hold)
                if not booted and not hold and 'deep sleep' in (err or ''):  # turned itself off: Power was let go too soon
                    hold, run_dir = 3000, run_dir + '-hold'
                    booted, keys, err = boot(eq, path, model, run_dir, hold)
                print(f'{"PASS" if booted else "FAIL"} {bid}' + (' (keys work)' if keys else '') + (f': {err}' if err and not booted else ''))
                sheet.append((bid, booted, keys, err, run_dir))
                if booted:
                    found.append({
                        'id': bid, 'name': c['name'], 'repo': c['repo'], 'ref': c['tag'], 'model': model, 'frame': FRAME[model],
                        'machine': MACHINE[model], 'licence': c['licence'], 'url': url, 'size': os.path.getsize(path),
                        'sha256': sha256(path), 'copy': c.get('copy', True), 'power_hold': hold, 'keys': keys,
                        'file': asset if not asset.startswith('https:') else None,
                    })
    found = keep + found
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'schema': 1, 'emulator': 'eink-qemu', 'builds': found}, f, indent=1, ensure_ascii=False)
        f.write('\n')
    with open(os.path.join(work, 'sheet.html'), 'w', encoding='utf-8') as f:
        f.write('<meta charset="utf-8"><style>div{display:inline-block;margin:6px;font:12px sans-serif;width:250px;vertical-align:top}'
                'img{width:120px;border:1px solid #888}</style>')
        for bid, booted, keys, err, run_dir in sheet:
            imgs = ''.join(f'<img src="{html.escape(os.path.relpath(os.path.join(run_dir, "shots", s + ".png"), work))}">'
                           for s in ('boot', 'down') if os.path.exists(os.path.join(run_dir, 'shots', s + '.png')))
            f.write(f'<div><b>{"PASS" if booted else "FAIL"}</b> {html.escape(bid)}{" · keys" if keys else ""}'
                    f'<br>{imgs}<br>{html.escape(err or "") if not booted else ""}</div>')
    print(f'{len(found)} builds in {os.path.normpath(OUT)}')


if __name__ == '__main__':
    main()
