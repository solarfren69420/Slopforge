"""Small standard-library GitHub client. Tokens only go to api.github.com."""
import base64
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import quote


class APIError(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f'GitHub HTTP {status}: {message}')


class GitHub:
    def __init__(self, token=None):
        self.token = os.environ.get('GH_TOKEN', '') if token is None else token

    def request(self, path, method='GET', data=None, missing_ok=False):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Expected a GitHub API path')
        headers = {'User-Agent': 'Slopforge-automation/1.0', 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        body = None if data is None else json.dumps(data).encode()
        if body is not None:
            headers['Content-Type'] = 'application/json'
        # Disable redirects: never forward a token to an upstream location.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        for attempt in range(3):
            try:
                req = urllib.request.Request('https://api.github.com' + path, data=body,
                                             headers=headers, method=method)
                with opener.open(req, timeout=30) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as error:
                if error.code == 404 and missing_ok:
                    return None
                # GitHub repository moves redirect within its API.
                if error.code in (301, 302, 307, 308) and method == 'GET':
                    location = error.headers.get('Location', '')
                    if location.startswith('https://api.github.com/'):
                        return self.request(location.removeprefix('https://api.github.com'), missing_ok=missing_ok)
                retry = error.code in (429, 500, 502, 503, 504) or (error.code == 403 and error.headers.get('Retry-After'))
                if retry and attempt < 2:
                    delay = min(60, max(2, int(error.headers.get('Retry-After', 2 ** (attempt + 1)))))
                    time.sleep(delay)
                    continue
                # Never print request headers or token values.
                try:
                    message = json.loads(error.read()).get('message', error.reason)
                except (ValueError, AttributeError):
                    message = error.reason
                if self.token: message = str(message).replace(self.token, '[redacted]')
                raise APIError(error.code, str(message)[:500]) from None
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == 2:
                    raise APIError(0, 'Network request failed') from error
                time.sleep(2 ** (attempt + 1))

    def pages(self, path, maximum=20):
        separator = '&' if '?' in path else '?'
        for page in range(1, maximum + 1):
            items = self.request(f'{path}{separator}per_page=100&page={page}')
            yield from items
            if len(items) < 100:
                return
        raise RuntimeError('Pagination limit reached; refusing to silently truncate results')


def content_bytes(item):
    if item.get('encoding') != 'base64':
        raise ValueError('Expected an inline GitHub content response')
    return base64.b64decode(item['content'])


def component(value):
    return quote(str(value), safe='')
