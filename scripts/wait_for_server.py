"""Wait briefly for the browser test server, failing clearly if startup fails."""
import sys
import time
import urllib.error
import urllib.request

for attempt in range(30):
    try:
        with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
            if response.status == 200:
                break
    except (urllib.error.URLError, TimeoutError):
        time.sleep(0.5)
else:
    raise SystemExit('Browser test server did not become ready')
