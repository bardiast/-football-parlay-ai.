"""Supabase Auth and user-scoped PostgREST persistence (publishable key only)."""
import requests
import pandas as pd
from datetime import datetime, timezone

class DBError(Exception):pass

class Database:
    def __init__(self,url,key,token=None):
        self.url=url.rstrip('/');self.key=key;self.token=token
    def _call(self,method,path,payload=None,params=None,extra=None):
        headers={'apikey':self.key,'Content-Type':'application/json'}
        if self.token:headers['Authorization']='Bearer '+self.token
        if extra:headers.update(extra)
        try:
            r=requests.request(method,self.url+path,headers=headers,json=payload,params=params,timeout=20)
            if r.status_code>=400:
                try:msg=r.json().get('message') or r.json().get('msg') or r.json().get('error_description') or r.json().get('error')
                except ValueError:msg=r.text[:180]
                raise DBError(f'{r.status_code}: {msg}')
            return r.json() if r.content else []
        except requests.RequestException as e:raise DBError('Supabase connection failed: '+str(e)) from e
    def login(self,email,password):return self._call('POST','/auth/v1/token',{'email':email,'password':password},params={'grant_type':'password'})
    def signup(self,email,password):return self._call('POST','/auth/v1/signup',{'email':email,'password':password})
    def rows(self,table,params=None):return self._call('GET','/rest/v1/'+table,params=params or {'select':'*'})
    def upsert(self,table,rows,conflict):
        if not rows:return []
        return self._call('POST','/rest/v1/'+table,rows,params={'on_conflict':conflict},extra={'Prefer':'resolution=ignore-duplicates,return=representation'})
    def delete(self,table,row_id):return self._call('DELETE','/rest/v1/'+table,params={'id':'eq.'+str(row_id)})
    def update(self,table,row_id,data):return self._call('PATCH','/rest/v1/'+table,data,params={'id':'eq.'+str(row_id)},extra={'Prefer':'return=representation'})

def prediction_records(frame,user_id):
    now=datetime.now(timezone.utc).isoformat(); records=[]
    for _,r in frame.iterrows():
        kickoff=pd.to_datetime(r.get('kickoff_utc'),utc=True,errors='coerce')
        if pd.isna(kickoff) or kickoff.to_pydatetime()<=datetime.now(timezone.utc):continue
        p=pd.to_numeric(r.get('probability'),errors='coerce')
        if pd.isna(p) or not 0<=float(p)<=1:continue
        o=pd.to_numeric(r.get('odds'),errors='coerce')
        records.append({'user_id':user_id,'match_id':str(r['match_id']),'league':str(r['league']),
         'match':str(r['match']),'kickoff_utc':kickoff.isoformat(),'market':str(r['market']),
         'probability':float(p),'odds':float(o) if pd.notna(o) and o>1 else None,
         'bookmaker':str(r.get('bookmaker') or '') if pd.notna(r.get('bookmaker')) else None,
         'recorded_at_utc':now})
    return records

def settle_saved(db,history):
    from analytics import settle
    rows=db.rows('predictions',{'select':'*','result':'eq.Pending','limit':'2000'})
    if not rows:return 0
    settled=settle(pd.DataFrame(rows),history)
    count=0
    for _,row in settled.iterrows():
        if row['result'] in ('Won','Lost'):
            db.update('predictions',row['id'],{'result':row['result']});count+=1
    return count
