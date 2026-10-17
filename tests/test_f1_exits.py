"""V4 position tracking invariants. No network, no production database."""
from types import SimpleNamespace
import pytest
from app.config import Settings
from app.models import Candle
from app.automation.trading_engine import TradingAutomationEngine

class FakeRepository:
    def __init__(self): self.events=[]
    def record_exit_event(self, **kwargs):
        self.events.append(kwargs)
        return True

def build_trade(side):
    return dict(id=1,side=side,entry_reference=100.,stop_loss=(95. if side=='LONG' else 105.),
                tp1=(105. if side=='LONG' else 95.), tp2=(110. if side=='LONG' else 90.),
                tp3=(115. if side=='LONG' else 85.),notional_usd=1000.,remaining_fraction=1.,
                tp1_hit_at=None,tp2_hit_at=None,tp3_hit_at=None,status='OPEN')

def build_engine():
    engine=object.__new__(TradingAutomationEngine)
    engine.settings=Settings()
    engine.repository=FakeRepository()
    return engine

@pytest.mark.parametrize('side', ['LONG','SHORT'])
def test_same_candle_stop_has_priority_over_tp(side):
    engine=build_engine(); trade=build_trade(side)
    candle=Candle(0,300_000,100,115,85,100,10)
    engine._process_trade_candle(trade,candle)
    assert [e['event_type'] for e in engine.repository.events]==['SL']
    assert engine.repository.events[0]['fraction_closed']==1.
    assert trade['status']=='CLOSED' and trade['remaining_fraction']==0.
    assert trade.get('tp1_hit_at') is None

@pytest.mark.parametrize('side', ['LONG','SHORT'])
def test_three_targets_close_in_order(side):
    engine=build_engine(); trade=build_trade(side)
    candle=Candle(0,300_000,100,116 if side=='LONG' else 101,99 if side=='LONG' else 84,105,10)
    engine._process_trade_candle(trade,candle)
    assert [e['event_type'] for e in engine.repository.events]==['TP1','TP2','TP3']
    assert [e['fraction_closed'] for e in engine.repository.events]==pytest.approx([.3,.3,.4])
    assert trade['status']=='CLOSED'
    assert trade['remaining_fraction']==pytest.approx(0)
    engine._process_trade_candle(trade,candle)
    assert len(engine.repository.events)==3

@pytest.mark.parametrize('side', ['LONG','SHORT'])
def test_only_first_target_then_stop_remaining(side):
    engine=build_engine();trade=build_trade(side)
    first=Candle(0,300_000,100,106 if side=='LONG' else 102,99 if side=='LONG' else 94,105,10)
    engine._process_trade_candle(trade,first)
    assert [e['event_type'] for e in engine.repository.events]==['TP1']
    assert trade['remaining_fraction']==pytest.approx(.7)
    second=Candle(300_000,600_000,100,102 if side=='LONG' else 106,94 if side=='LONG' else 98,100,10)
    engine._process_trade_candle(trade,second)
    assert [e['event_type'] for e in engine.repository.events]==['TP1','SL']
    assert engine.repository.events[-1]['fraction_closed']==pytest.approx(.7)
    assert trade['status']=='CLOSED'