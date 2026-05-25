"""Check if bilibili config has valid cookie. Exit 0 if yes, 1 if no."""
import json, os, sys

CONFIG_FILE = os.path.expanduser(r'~\.hermes\bilibili_config.json')

if not os.path.exists(CONFIG_FILE):
    sys.exit(1)

try:
    cfg = json.load(open(CONFIG_FILE, encoding='utf-8'))
except (json.JSONDecodeError, UnicodeDecodeError):
    sys.exit(1)

cookie = cfg.get('cookie', '')
if cookie and 'SESSDATA' in cookie:
    sys.exit(0)
else:
    sys.exit(1)
