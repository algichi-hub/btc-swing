"""In-memory transactional contract tests for the real F5 dispatcher.

No Neon credentials or external Push provider required.
"""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from app.notifications import trade_dispatcher as td

class Result:
    def __init__(self, rows=()):
        self.rows=list(rows)
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None

class DB:
    def __init__(self):
        self.event={"id":1,"public_payload":{"kind":"TRADE_EVENT","event":"OPEN",
                    "title":"BTC Swing V5","id":"example"},"attempts":0,
                    "expires_at":datetime.now(timezone.utc)+timedelta(hours=1)}
        self.status="PENDING"
        self.devices={10:True}
        self.deliveries={}
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,params=()):
        q=" ".join(sql.upper().split())
        if "SELECT ID,PUBLIC_PAYLOAD,ATTEMPTS,EXPIRES_AT FROM V5_PUSH_OUTBOX" in q:
            return Result([self.event.copy()] if self.status=="PENDING" else [])
        if "SELECT NOW()>=" in q: return Result([{"expired":False}])
        if "SELECT ID FROM V5_PUSH_SUBSCRIPTIONS" in q:
            return Result([{"id":k} for k,v in self.devices.items() if v])
        if "INSERT INTO V5_PUSH_DELIVERIES" in q:
            key=params[1]
            self.deliveries.setdefault(key,{"state":"PENDING","attempts":0,"last_error_code":None})
            return Result()
        if "UPDATE V5_PUSH_DELIVERIES D SET STATE='EXPIRED'" in q:
            for k,d in self.deliveries.items():
                if not self.devices.get(k,False) and d["state"]=="PENDING":
                    d["state"]="EXPIRED"
                    d["last_error_code"]="SUBSCRIPTION_REVOKED"
            return Result()
        if "FROM V5_PUSH_DELIVERIES D JOIN V5_PUSH_SUBSCRIPTIONS S" in q:
            return Result([{"subscription_id":k,"attempts":v["attempts"],
                "endpoint_ciphertext":b"x","p256dh_ciphertext":b"x",
                "auth_ciphertext":b"x"} for k,v in self.deliveries.items()
                if v["state"]=="PENDING" and self.devices.get(k,False)])
        if "UPDATE V5_PUSH_SUBSCRIPTIONS SET ACTIVE=FALSE" in q:
            self.devices[params[0]]=False
            return Result()
        if "UPDATE V5_PUSH_DELIVERIES SET STATE=" in q:
            state,attempts,code,_,_,key=params
            self.deliveries[key].update(state=state,attempts=attempts,last_error_code=code)
            return Result()
        if "SELECT COUNT(*) AS N FROM V5_PUSH_DELIVERIES" in q:
            wanted="PENDING" if "STATE='PENDING'" in q else "FAILED"
            return Result([{"n":sum(x["state"]==wanted for x in self.deliveries.values())}])
        if "UPDATE V5_PUSH_OUTBOX SET ATTEMPTS=ATTEMPTS+1" in q:
            self.event["attempts"]+=1
            return Result()
        if "UPDATE V5_PUSH_OUTBOX SET STATUS=" in q:
            self.status=params[0]
            return Result()
        raise AssertionError("Unexpected SQL: "+q[:180])

def setup(monkeypatch):
    monkeypatch.setenv("BTC_PROCESS_ROLE","push_dispatcher")
    monkeypatch.setenv("PUSH_REAL_EVENTS_ENABLED","true")
    monkeypatch.setenv("PUSH_DISPATCHER_REAL_SEND","true")
    db=DB()
    monkeypatch.setattr(td,"connect_pg",lambda:db)
    return db

def test_429_retry_then_success_without_duplicate(monkeypatch):
    db=setup(monkeypatch)
    calls=[]
    def send(sub,payload):
        calls.append(sub["subscription_id"])
        if len(calls)==1:
            raise RuntimeError("HTTP 429 test simulation")
    monkeypatch.setattr(td,"_send",send)
    assert td.drain_real_events()["processed"]==1
    assert db.status=="PENDING"
    assert db.deliveries[10]["attempts"]==1
    assert db.event["attempts"]==1
    assert td.drain_real_events()["processed"]==1
    assert db.status=="SENT"
    assert db.deliveries[10]["attempts"]==2
    assert td.drain_real_events()["processed"]==0
    assert calls==[10,10]

def test_terminal_410_deactivates_device(monkeypatch):
    db=setup(monkeypatch)
    class Gone(Exception):
        response=SimpleNamespace(status_code=410)
    def reject(*args): raise Gone()
    monkeypatch.setattr(td,"_send",reject)
    td.drain_real_events()
    assert db.devices[10] is False
    assert db.deliveries[10]["state"]=="EXPIRED"
    assert db.deliveries[10]["last_error_code"]=="SUBSCRIPTION_GONE"
    assert db.status=="SENT"

def test_revocation_finishes_pending_and_no_new_recipient(monkeypatch):
    db=setup(monkeypatch)
    def temporary(*args): raise RuntimeError("provider offline")
    monkeypatch.setattr(td,"_send",temporary)
    td.drain_real_events()
    assert db.status=="PENDING"
    db.devices[10]=False
    db.devices[11]=True
    td.drain_real_events()
    assert db.deliveries[10]["state"]=="EXPIRED"
    assert 11 not in db.deliveries
    assert db.status=="SENT"

def test_retries_exhaust_with_failure(monkeypatch):
    db=setup(monkeypatch)
    def temporary(*args): raise RuntimeError("provider 503")
    monkeypatch.setattr(td,"_send",temporary)
    for _ in range(5): td.drain_real_events()
    assert db.status=="FAILED"
    assert db.deliveries[10]["state"]=="FAILED"
    assert db.deliveries[10]["attempts"]==5
    assert db.deliveries[10]["last_error_code"]=="RETRY_EXHAUSTED"
