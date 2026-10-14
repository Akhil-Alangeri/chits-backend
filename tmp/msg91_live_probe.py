"""Live customer send, with sanitized transport diagnostics only."""
import asyncio,json,re
from unittest.mock import patch
import httpx
from fastapi import HTTPException
from app.core.database import SessionLocal
from app.services.customer.msg91_auth import msg91_auth_service as service
original=httpx.AsyncClient.request
async def traced(self,method,url,**kwargs):
    print('OUTBOUND',json.dumps({'method':method,'host':str(url).split('/')[2],'mobile_masked':'91XXXXXX0526','parameters':{k:v for k,v in kwargs.get('params',{}).items() if k not in ('mobile','otp','authkey')}}))
    response=await original(self,method,url,**kwargs)
    try: data=response.json()
    except ValueError: data={}
    safe={k:data.get(k) for k in ('type','code','request_id','requestId') if k in data}
    message=str(data.get('message','')).lower()
    category='accepted' if data.get('type')=='success' else 'provider_error'
    if 'auth' in message:category='provider_authentication_error'
    elif 'template' in message or 'flow id' in message:category='provider_template_error'
    elif 'balance' in message or 'credit' in message:category='provider_balance_error'
    elif 'ip' in message:category='provider_ip_error'
    if data.get('type') != 'success':
        summary=str(data.get('message',''))
        key=kwargs.get('headers',{}).get('authkey','')
        if key: summary=summary.replace(key,'[redacted]')
        summary=re.sub(r'[0-9]{4,}|[A-Za-z0-9]{16,}','[redacted]',summary)
        safe['error_summary']=summary[:250]
    safe.update(http_status=response.status_code,category=category)
    print('PROVIDER',json.dumps(safe))
    return response
async def main():
    with SessionLocal() as db:
        with patch.object(httpx.AsyncClient,'request',traced):
            try:
                result=await service.send(db,'7288010526')
                print('RESULT',json.dumps(result))
            except HTTPException as error:
                print('RESULT',json.dumps({'status':error.status_code,'detail':error.detail}))
asyncio.run(main())
