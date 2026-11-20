"""Shared utilities for honest README demos: real UI, isolated fictional data."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import sys
import threading

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

DEMO_TIME = datetime(2026, 11, 20, 4, 0, tzinfo=timezone.utc)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['SECRET_KEY'] = 'fictional-local-demo-only'
os.environ['MONGO_URI'] = 'mongodb://localhost:27017'
os.environ['MONGO_DBNAME'] = 'portfolio_demo'
os.environ['MONGODB_URL'] = 'mongodb://localhost:27017/noise_monitor'


def options(script, filename):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(script).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--browser', help='Optional Chromium/Chrome executable')
    args = parser.parse_args()
    args.root = args.root.resolve()
    args.output = args.output or args.root / 'docs/media' / filename
    return args


def load(name, path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def font(size, mono=False):
    names = (['/System/Library/Fonts/Menlo.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']
             if mono else ['/System/Library/Fonts/Supplemental/Arial.ttf',
                           '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'])
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default(size=size)


def save_gif(frames, durations, output):
    # One palette across all frames avoids color flicker between pages.
    samples = frames[::max(1, len(frames) // 20)]
    sheet = Image.new('RGB', (250 * 5, 200 * ((len(samples) + 4) // 5)))
    for i, frame in enumerate(samples):
        thumb = frame.copy()
        thumb.thumbnail((250, 200))
        sheet.paste(thumb, ((i % 5) * 250, (i // 5) * 200))
    palette = sheet.quantize(colors=256)
    images = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    output.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(output, save_all=True, append_images=images[1:],
                   duration=durations, loop=0, optimize=True, disposal=2)
    with Image.open(output) as check:
        info = {'file': output.name, 'size': list(check.size), 'frames': check.n_frames,
                'bytes': output.stat().st_size,
                'duration_ms': sum(durations)}
    print(json.dumps(info), flush=True)


@contextmanager
def browser_session(app, args):
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            executable = args.browser
            if not executable:
                mac = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
                executable = str(mac) if mac.exists() else None
            browser = playwright.chromium.launch(headless=True, executable_path=executable)
            context = browser.new_context(viewport={'width': 1200, 'height': 800},
                                          device_scale_factor=1, timezone_id='Asia/Shanghai')
            page = context.new_page()
            page.clock.set_fixed_time(DEMO_TIME)
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            try:
                yield context, page, f'http://127.0.0.1:{server.server_port}'
            finally:
                print('Browser errors:', json.dumps(sorted(set(errors))), flush=True)
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


class Recorder:
    def __init__(self, page, title, subtitle):
        self.page, self.title, self.subtitle = page, title, subtitle
        self.frames, self.durations = [], []

    def snap(self, step, duration=500, point=None):
        raw = self.page.screenshot(animations='disabled')
        shot = Image.open(io.BytesIO(raw)).convert('RGB').resize((1000, 667), Image.Resampling.LANCZOS)
        frame = Image.new('RGB', (1000, 796), '#101a2b')
        frame.paste(shot, (0, 86))
        draw = ImageDraw.Draw(frame)
        draw.text((24, 13), self.title, fill='#eef6ff', font=font(27))
        draw.text((25, 51), step, fill='#67e8c2', font=font(18))
        draw.rounded_rectangle((717, 18, 978, 53), radius=8, fill='#253349')
        draw.text((730, 27), 'LOCAL UI / FICTIONAL DATA', fill='#d7e2ef', font=font(16))
        draw.text((24, 768), self.subtitle + '  |  Playback timing edited', fill='#bdcde1', font=font(15))
        if point:
            x, y = point[0] * 1000 / 1200, 86 + point[1] * 667 / 800
            draw.ellipse((x-11, y-11, x+11, y+11), outline='#009775', width=3)
        self.frames.append(frame)
        self.durations.append(duration)

    def type(self, selector, text, step, chunks=7):
        locator = self.page.locator(selector).first
        locator.scroll_into_view_if_needed()
        locator.fill('')
        for i in range(1, chunks + 1):
            locator.fill(text[:max(1, round(len(text) * i / chunks))])
            self.page.wait_for_timeout(45)
            self.snap(step, 140)
        self.snap(step, 600)

    def click(self, selector, step):
        target = self.page.locator(selector).first
        target.scroll_into_view_if_needed()
        box = target.bounding_box()
        point = (box['x'] + box['width']/2, box['y'] + box['height']/2)
        self.snap(step, 350, point=point)
        target.click()
        self.page.wait_for_timeout(150)

    def scroll(self, y, step):
        start = self.page.evaluate('window.scrollY')
        for i in range(1, 7):
            self.page.evaluate('(y) => window.scrollTo(0, y)', start + (y-start)*i/6)
            self.snap(step, 90)

    def save(self, output):
        save_gif(self.frames, self.durations, output)
