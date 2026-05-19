import asyncio
import aiohttp
import time
import hmac
import base64
import hashlib
import json

API_KEY = "bg_fbe3193357bb1edfaac91bb306495efe"
API_SECRET = "1a7db93bbd9f407275cadce1b307b26af247bfd8032161de5caf8ea4daf75200"
PASSPHRASE = "kirizek1985"

def gen_sign(timestamp, method, request_path, query_string, body):
    pre_hash = timestamp + method.upper() + request_path
    if query_string:
        pre_hash += '?' + query_string
    pre_hash += body
    signature = hmac.new(API_SECRET.encode('utf-8'), pre_hash.encode('utf-8'), hashlib.sha256).digest()
    return base64.b64encode(signature).decode()

async def test():
    endpoint = '/api/v2/spot/account/assets'
    url = f'https://api.bitget.com{endpoint}'
    timestamp = str(int(time.time() * 1000))
    sign = gen_sign(timestamp, 'GET', endpoint, '', '')
    headers = {
        'ACCESS-KEY': API_KEY,
        'ACCESS-SIGN': sign,
        'ACCESS-PASSPHRASE': PASSPHRASE,
        'ACCESS-TIMESTAMP': timestamp,
        'paptrading': '1',
        'Content-Type': 'application/json'
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            print("Status:", resp.status)
            print("Response:", text[:500])

asyncio.run(test())