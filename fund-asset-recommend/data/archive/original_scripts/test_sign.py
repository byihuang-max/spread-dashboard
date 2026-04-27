#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import urllib.parse
import time

appid = 'hfnogbr8zceiiygdkhw'
appkey = 'c6e941fd6aad65ceede2d780262d11ee'

params = {
    "type": 3,
    "page": 1,
    "pagesize": 50,
    "app_id": appid
}

# 按照SDK的签名逻辑重新生成
sign_dict = dict(filter(lambda item: True if item[1] is not None else False, params.items()))
signed_str = ''
for key in sorted(sign_dict):
    if key.lower() == 'sign':
        continue
    signed_str += '&' + key + '=' + urllib.parse.quote(str(params[key]).encode('utf-8'))
signed_str = signed_str[1:]
signed_str += appkey

print("签名字符串:")
print(signed_str)
print("\nMD5签名:")
sign = hashlib.md5(signed_str.encode('utf-8')).hexdigest().lower()
print(sign)
