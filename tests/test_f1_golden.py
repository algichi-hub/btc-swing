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
    "app/indicators/stoch_rsi.py":"f907729e688f389a6c1fdb9cbfa1f8663699d58476b40da48150b1a70ac62edb",
    "app/indicators/volume.py":"f3e1408ed8dc2231e18938bf35c91b86589ed446279353b5cf4e102e47d80e91",
    "app/strategy/dashboard.py":"39fb37f60554c7edfbc1a21475a620058fafd9807edd98b2e802a7bf8d82c89b",
    "app/strategy/swing_range.py":"e2670db7da6bbd826ffc3eb596920c29b5b2aa8e2b681ba7b0055bfa77cab2ba",
    "app/strategy/trade_plan.py":"7c242aef00376758e283332d5fb91a389e1e3cd33d6a8ee029c5ec56bae51e28",
    "app/portfolio/sizing.py":"1f350ef018ebe2f72d89a4e08c8b26b3a1ba3e636994fc72c15ec4034da38a5f",
    "app/automation/trading_engine.py":"89772de10262f9d0d51990ff12576fe2b7cc274cdf5692726b943db4f56913cd",
    }
    root = Path(__file__).resolve().parents[1]
    for p,h in expected.items():
        assert hashlib.sha256((root/p).read_bytes()).hexdigest()==h,p