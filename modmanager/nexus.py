import json
import urllib.error
import urllib.parse
import urllib.request
import re


class Nexus:
    base = 'https://api.nexusmods.com/v1'

    def __init__(self):
        self.key = ''

    def request(self, route, params=None):
        if not self.key:
            raise ValueError('请先在设置中连接 Nexus Mods API Key。')
        url = self.base + route
        if params:
            url += '?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={
            'apikey': self.key, 'Accept': 'application/json',
            'User-Agent': 'ModHarbor/0.1.0', 'Application-Name': 'ModHarbor', 'Application-Version': '0.1.0'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            messages = {401: 'Nexus API Key 无效。', 403: 'Nexus 拒绝访问；自动下载通常需要 Premium 会员。',
                        404: '未找到该游戏、MOD 或文件。', 429: 'Nexus API 请求额度已用完，请稍后重试。'}
            raise ValueError(messages.get(exc.code, f'Nexus API 返回 HTTP {exc.code}。')) from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError('无法连接 Nexus Mods，请检查网络后重试。') from None

    @staticmethod
    def domain(value):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', value or ''):
            raise ValueError('请选择有 Nexus 游戏域名的游戏。')
        return value

    def validate(self):
        data = self.request('/users/validate.json')
        return {'name': data.get('name', 'Nexus 用户'), 'premium': bool(data.get('is_premium'))}

    def browse(self, domain, query='', category='trending'):
        domain = self.domain(domain)
        if query.strip().isdigit():
            return [self.request(f'/games/{domain}/mods/{int(query)}.json')]
        endpoints = {'trending': 'trending', 'latest': 'latest_added', 'updated': 'latest_updated'}
        endpoint = endpoints.get(category, 'trending')
        result = self.request(f'/games/{domain}/mods/{endpoint}.json')
        query = query.casefold().strip()
        return [m for m in result if query in (m.get('name', '') + ' ' + m.get('summary', '')).casefold()]

    def files(self, domain, mod_id):
        return self.request(f'/games/{self.domain(domain)}/mods/{int(mod_id)}/files.json')

    def download_link(self, domain, mod_id, file_id):
        links = self.request(f'/games/{self.domain(domain)}/mods/{int(mod_id)}/files/{int(file_id)}/download_link.json')
        if not links or not links[0].get('URI'):
            raise ValueError('Nexus 未返回可用下载地址。')
        return links[0]['URI']

    def mod(self, domain, mod_id):
        return self.request(f'/games/{self.domain(domain)}/mods/{int(mod_id)}.json')
