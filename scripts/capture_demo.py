"""Record real SoundWatch pages with explicitly synthetic measurements."""
from types import SimpleNamespace
import mongomock
from demo_capture import DEMO_TIME, Recorder, browser_session, load, options


def main():
    args = options(__file__, 'soundwatch-workflow.gif')
    module = load('soundwatch_demo_app', args.root / 'web-app/app.py')
    module.app.config['_MONGO_CLIENT'] = mongomock.MongoClient('mongodb://localhost/noise_monitor')
    now = DEMO_TIME.timestamp()
    module.time = SimpleNamespace(time=lambda: now)
    rows = []
    for i in range(45):
        level = round(29 + (i % 17) * 1.25, 1)
        rows.append({'ts': now - (45-i)*20, 'rms_db': level,
                     'label': 'quiet' if level < 33 else 'normal'})
    module.measurements().insert_many(rows)
    with browser_session(module.app, args) as (_, page, base):
        rec = Recorder(page, 'SoundWatch', 'Synthetic readings / no microphone recording')
        page.goto(base + '/dashboard', wait_until='networkidle')
        page.wait_for_function("document.querySelector('#current-decibels').textContent.includes('dB')")
        rec.snap('01 / Inspect the current reading', 1500)
        # Actual DB inserts followed by the app's own API/UI refresh functions.
        values = [(30.0, 'quiet'), (32.5, 'quiet'), (38.0, 'normal'),
                  (43.5, 'normal'), (49.0, 'normal'), (56.0, 'loud'),
                  (62.0, 'loud'), (57.5, 'loud'), (45.0, 'normal'), (33.0, 'quiet')]
        for i, (value, label) in enumerate(values):
            module.measurements().insert_one({'ts': now+i+1, 'rms_db': value, 'label': label})
            page.evaluate('updateCurrentStatus(); updateStatistics();')
            page.wait_for_function('(v) => document.querySelector("#current-decibels").textContent === v',
                                   arg=f'{value:.1f} dB')
            rec.snap('02 / Watch readings and labels update', 470)
        rec.scroll(500, '03 / Explore the recent trend')
        page.wait_for_function('noiseHistoryChart && noiseHistoryChart.data.datasets[0].data.length === 55',
                               timeout=10000)
        rec.snap('03 / Explore the recent trend', 1600)
        page.goto(base + '/history', wait_until='networkidle')
        page.locator('#history-table').wait_for(state='visible')
        assert page.locator('#history-table tbody tr').count() == 55
        rec.snap('04 / Inspect measurement history', 1300)
        rec.scroll(350, '04 / Inspect measurement history')
        rec.snap('04 / Inspect measurement history', 1600)
        rec.save(args.output)
    print('Verified: 10 current-reading updates and 55 history records')


if __name__ == '__main__':
    main()
