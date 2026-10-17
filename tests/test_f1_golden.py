import json,math,hashlib,sys
from pathlib import Path
from app.config import Settings
from app.models import Candle
from app.indicators.stoch_rsi import stochastic_rsi
from app.indicators.volume import relative_volume
from app.strategy.dashboard import _derive_signal,_build_trade_plan,build_dashboard_state
from app.strategy.trade_plan import validate_trade_plan_topology,reward_risk,weighted_rr
from app.portfolio.sizing import recommend_sizing,NoValidSizingError
from app.automation.trading_engine import calculate_fraction_pnl_usd,calculate_fraction_pnl_r,compute_daily_summary_window
from datetime import datetime,timezone
settings=Settings()
base=1700000000000
cases={}
closes=[44000+100*math.sin(i*.36)+55*math.sin(i*.13)+i*0.5 for i in range(120)]
closes_down=[47000-i*12+25*math.cos(i/5) for i in range(120)]
for name,values in [('oscillating',closes),('downtrend',closes_down),('flat',[44000.]*120),('short',[100.]*15)]:
 cases['stoch_'+name]=stochastic_rsi(values)
vols=[10+i%4 for i in range(24)]
candles=[Candle(base+i*3600000,base+(i+1)*3600000,100,105,95,100+i*.5,v) for i,v in enumerate(vols)]
for name,vol in [('nominal',15),('spike',100),('zero',0)]:
 cs=[*candles[:-1],Candle(base+23*3600000,base+24*3600000,100,105,95,100,vol)]
 cases['relvol_'+name]=relative_volume(cs,20)
cases['relvol_short']=relative_volume(candles[:10],20)
for side,entry,stop,target in [('LONG',100,95,110),('SHORT',100,105,90),('LONG',100,100,110),('SHORT',100,100,95)]:
 cases['rr_'+side+'_'+str(stop)]=reward_risk(side,entry,stop,target)
for side,entry,stop,tps in [('LONG',100,95,(105,110,120)),('SHORT',100,105,(95,90,80)),('LONG',100,105,(110,120,130)),('SHORT',100,95,(90,80,70))]:
 cases['topology_'+side+'_'+str(stop)]=validate_trade_plan_topology(side,entry,stop,*tps)
for name,kwargs in [('long_watch',dict(price=102,support=100,resistance=120,position_pct=10,volume_1h_relative=0.9,stoch_rsi_1h={'k':15,'d':20})),('long_confirm',dict(price=102,support=100,resistance=120,position_pct=10,volume_1h_relative=1.1,stoch_rsi_1h={'k':15,'d':13})),('short_confirm',dict(price=118,support=100,resistance=120,position_pct=90,volume_1h_relative=1.10,stoch_rsi_1h={'k':80,'d':85})),('neutral',dict(price=110,support=100,resistance=120,position_pct=50,volume_1h_relative=1.5,stoch_rsi_1h={'k':15,'d':10})),('invalid_range',dict(price=110,support=110,resistance=100,position_pct=10,volume_1h_relative=1.5,stoch_rsi_1h={'k':15,'d':10})),('threshold_exact',dict(price=102,support=100,resistance=120,position_pct=10,volume_1h_relative=1.05,stoch_rsi_1h={'k':15,'d':10})),('threshold_below',dict(price=102,support=100,resistance=120,position_pct=10,volume_1h_relative=1.04999,stoch_rsi_1h={'k':15,'d':10}))]:
 signal,candidate=_derive_signal(settings=settings,**kwargs)
 plan,error=_build_trade_plan(signal['state'],candidate,settings) if candidate else (None,None)
 cases['signal_'+name]={'signal':signal,'candidate':candidate,'plan':plan,'error':error}
for side,exit_price in [('LONG',110),('LONG',95),('SHORT',90),('SHORT',105)]:
 key='pnl_'+side+'_'+str(exit_price)
 cases[key]={'usd':calculate_fraction_pnl_usd(side=side,entry=100,exit_price=exit_price,notional_usd=1000,fraction_closed=.3),'r':calculate_fraction_pnl_r(side=side,entry=100,stop_loss=(95 if side=='LONG' else 105),exit_price=exit_price,notional_usd=1000,fraction_closed=.3)}
for stamp in ['2026-03-29T11:00:00+00:00','2026-10-25T11:00:00+00:00']:
 a=compute_daily_summary_window(datetime.fromisoformat(stamp),'Europe/Madrid',report_hour=7,report_minute=0)
 cases['dst_'+stamp]=[x.isoformat() for x in a]
for name,prices in [('long', (100.,96.)),('short',(100.,104.)),('invalid',(100.,100.))]:
 try:cases['sizing_'+name]=recommend_sizing(*prices,'HIGH',settings,side='SHORT' if name=='short' else 'LONG')
 except NoValidSizingError as e:cases['sizing_'+name]={'error':e.reason}
# fixture deterministic OHLCV for full dashboard including pivot engine
for name,shift in [('range',0),('volatile',800)]:
 daily=[]
 for i in range(75):
  p=44000+shift+550*math.sin(i*.75)+200*math.cos(i*.27)
  daily.append(Candle(base+i*86400000,base+(i+1)*86400000, p-70,p+300,p-300,p,12+i%5))
 hourly=[]
 for i in range(45):
  p=44000+shift+100*math.sin(i*.5)
  hourly.append(Candle(base+i*3600000,base+(i+1)*3600000,p,p+100,p-100,p, 12+i%5))
 state=build_dashboard_state(price=daily[-1].close,daily_candles=daily,hourly_candles=hourly,settings=settings,now=datetime(2026,10,17,12,tzinfo=timezone.utc),daily_candles_used=45)
 cases['dashboard_'+name]=state

import pytest

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "golden_v4.json").read_text(encoding="utf-8"))

def compare(actual, expected, path="root"):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), (path, type(actual))
        assert actual.keys() == expected.keys(), (path, actual.keys(), expected.keys())
        for k, v in expected.items(): compare(actual[k], v, f"{path}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, (list, tuple)) and len(actual)==len(expected), path
        for i,(a,e) in enumerate(zip(actual,expected)): compare(a,e,f"{path}[{i}]")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-12, abs=1e-10), (path,actual,expected)
    else:
        assert actual == expected, (path, actual, expected)

@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_v4_golden_master(case):
    compare(cases[case], GOLDEN[case], case)

def test_original_algorithm_hashes_unchanged():
    expected = {
    "app/indicators/stoch_rsi.py":"aacfe0c117e2d197cfde903ccb1376cbbe76ceef2a2cb33f98acbb3c8227b040",
    "app/indicators/volume.py":"164b923cf831df8c8e4fd3ab7c4c14c41cad780835799b1e0167b98b9bb7b82b",
    "app/strategy/dashboard.py":"002fb3589409b55edfe456f294c5ec7e6ce377b58431620bee114c7352c1526c",
    "app/strategy/swing_range.py":"63dc129c98c02b338b1257532f60d49b15cff893d6c9cc21efd3df5f6ac4daa2",
    "app/strategy/trade_plan.py":"5a0428a21588d07f3318e6daca82650b1885e8a2b84b0f31784b6e65a635c5c1",
    "app/portfolio/sizing.py":"fd6c28b50948c326b931244cabf9472e1b7197553db2c971999ae23db3c28b25",
    "app/automation/trading_engine.py":"2b95e188c45a882d1a584d1e9749533232346d1f90cd26bedb7c21350bb54ae9",
    }
    root = Path(__file__).resolve().parents[1]
    for p,h in expected.items():
        assert hashlib.sha256((root/p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()==h,p