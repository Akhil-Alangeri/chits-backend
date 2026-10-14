import httpx,re,json,html
for url in ['https://docs.msg91.com/otp/otp-logs','https://docs.msg91.com/otp/sendotp']:
    page=httpx.get(url,timeout=20).text
    for match in re.findall(r'self.__next_f.push\((.*?)\)</script>',page):
        try: chunk=json.loads(match)[1]
        except (ValueError,IndexError): continue
        tag='"pageContentDataSSR":'
        index=chunk.find(tag)
        if index<0: continue
        data,_=json.JSONDecoder().raw_decode(chunk[index+len(tag):])
        def clean(value):
            if isinstance(value,str):return html.unescape(re.sub('<[^>]+>','',value))
            if isinstance(value,dict):return {clean(k):clean(v) for k,v in value.items()}
            if isinstance(value,list):return [clean(v) for v in value]
            return value
        print(url,json.dumps(clean({k:data.get(k) for k in ['URL','params','headers','requestType','sampleResponse']})))
