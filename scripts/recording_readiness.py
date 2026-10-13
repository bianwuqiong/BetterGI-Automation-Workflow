"""Delay debug video until this native process has passed startup. No UI input."""
import argparse
import json
from pathlib import Path
import re

HEADER = re.compile(r'^\[\d{2}:\d{2}:\d{2}\.\d+\]\s+\[INF\]\s+\[[^\]\n]*:P(\d+)(?=:|\])[^\]\n]*\]\s+(BetterGenshinImpact\.[A-Za-z0-9_.]+)\s*$')
CONFIG = re.compile(r'(?:参数指定|启用)(?:的)?一条龙配置\s*[：:]\s*([A-Za-z0-9_-]+)\s*$')
READY = '检测到已进入主界面或可交互UI，结束启动等待'


def recording_startup_ready(text, pid, name):
    active = None
    for record in re.split(r'(?=^\[\d{2}:\d{2}:\d{2}\.\d+\])', text, flags=re.M):
        lines = record.splitlines()
        if not lines:
            continue
        header = HEADER.fullmatch(lines[0])
        if not header or int(header[1]) != pid:
            continue
        body = next((line.strip() for line in lines[1:] if line.strip()), '')
        config = CONFIG.fullmatch(body)
        if config and header[2] == 'BetterGenshinImpact.ViewModel.Pages.OneDragonFlowViewModel':
            active = config[1]
        if active == name and header[2] == 'BetterGenshinImpact.GameTask.Common.TaskControl' and body == READY:
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id) is None:
        return 1
    root = Path(args.root).resolve()
    directory = root/'logs/runs'/args.run_id
    try:
        result = json.loads((directory/'result.json').read_text(encoding='utf-8-sig'))
        if result.get('runId') != args.run_id or result.get('outcome') != 'running':
            return 1
        offsets = json.loads((directory/'log-offsets.json').read_text(encoding='utf-8-sig'))
        if __package__:
            from .workflow import collect_log
        else:
            from workflow import collect_log
        directories = {Path(p).parent for p in offsets}
        if len(directories) != 1:
            return 1
        text, _ = collect_log(next(iter(directories)), offsets, result['bettergiPid'])
        return 0 if recording_startup_ready(text, result['bettergiPid'], 'AutoGame_'+args.run_id) else 1
    except (OSError, KeyError, ValueError):
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
