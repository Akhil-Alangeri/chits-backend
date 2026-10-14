"""Read-only delivery lookup. Never prints secrets, OTPs or SMS contents."""
import json,os
import httpx
from dotenv import load_dotenv
load_dotenv()
params={'startDate':'2026-10-09','endDate':'2026-10-09','requestId':'366a696a6f634251336d3957','limit':10,'fields':'requestId,requestDate,status,statusCode,failureReason,pauseReason,senderId,DLT_TE_ID,templateID'}
try:
    r=httpx.get('https://control.msg91.com/api/v5/report/logs/p/otp',params=params,headers={'authkey':os.environ['MSG91_AUTH_KEY'],'accept':'application/json'},timeout=25)
    data=r.json()
    print('HTTP',r.status_code)
    if isinstance(data,dict):
        print(json.dumps({k:data[k] for k in ['data','error','errors','status','code','hasError'] if k in data},default=str))
    else: print('Unexpected response shape')
except httpx.RequestError as error:
    print('Network error:',type(error).__name__)
