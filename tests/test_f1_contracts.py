"""Independent invariants and boundary tests; reference fixture is in test_f1_golden.py."""
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from app.models import Candle
from app.config import Settings
from app.indicators.volume import relative_volume
from app.market.hyperliquid import closed_candles
from app.strategy.dashboard import _derive_signal,compute_position_pct
from app.strategy.trade_plan import validate_trade_plan_topology,reward_risk
from app.strategy.swing_range import split_daily_candles_for_swing
from app.automation.trading_engine import calculate_fraction_pnl_usd
from app.portfolio.sizing import recommend_sizing,NoValidSizingError


def candle(i, volume=10):
    return Candle(i*86_400_000, (i+1)*86_400_000, 100.,110.,90.,100.,volume)


@pytest.mark.parametrize('side,stop,tps,valid',[
    ('LONG',95,(105,110,120),True),
    ('LONG',100,(105,110,120),False),
    ('LONG',95,(105,105,120),False),
    ('SHORT',105,(95,90,80),True),
    ('SHORT',100,(95,90,80),False),
    ('SHORT',105,(95,96,80),False),
])
def test_topology_directional(side,stop,tps,valid):
    assert validate_trade_plan_topology(side,100,stop,*tps)[0] is valid


@pytest.mark.parametrize('side,target,expected', [('LONG',110,2),('SHORT',90,2),('LONG',90,0),('SHORT',110,0)])
def test_rr_nonnegative(side,target,expected):
    stop=95 if side=='LONG' else 105
    assert reward_risk(side,100,stop,target)==pytest.approx(expected)


def test_pnl_fraction_conservation_long_short():
    for side,exit_price in [('LONG',110),('SHORT',90)]:
        pieces=[calculate_fraction_pnl_usd(side=side,entry=100,exit_price=exit_price,notional_usd=1000,fraction_closed=f) for f in (.3,.3,.4)]
        full=calculate_fraction_pnl_usd(side=side,entry=100,exit_price=exit_price,notional_usd=1000,fraction_closed=1)
        assert sum(pieces)==pytest.approx(full)


def test_volume_threshold_and_missing_data():
    candles=[candle(i,10) for i in range(20)] + [candle(20,10.5)]
    assert relative_volume(candles)==pytest.approx(1.05)
    assert relative_volume(candles[:20]) is None
    assert relative_volume([candle(i,0) for i in range(21)]) is None


@pytest.mark.parametrize('relative,expected',[(1.049999,'WATCH'),(1.05,'HIGH')])
def test_threshold_boundary_does_not_promote_before_105(relative,expected):
    signal,_ = _derive_signal(price=102,support=100,resistance=120,position_pct=10,settings=Settings(),volume_1h_relative=relative,stoch_rsi_1h={'k':15,'d':10})
    assert signal['state'] != 'NO_TRADE'
    assert signal['state']=='WATCH' if expected=='WATCH' else signal['state'] in {'CONFIRMED','HIGH','VERY_HIGH'}


def test_invalid_range_no_trade_and_neutral():
    for price,support,resistance,position in [(110,120,100,10),(110,100,120,50)]:
        signal,candidate=_derive_signal(price=price,support=support,resistance=resistance,position_pct=position,settings=Settings(),volume_1h_relative=2.,stoch_rsi_1h={'k':15,'d':10})
        assert signal['state']=='NO_TRADE' and candidate is None


def test_closed_candles_reject_open_and_safety_window():
    now_ms=1_700_000_000_000
    cs=[Candle(now_ms-60_000*i,now_ms+(20_000-60_000*i),100,110,90,100,10) for i in range(4)]
    with patch('app.market.hyperliquid.time.time',return_value=now_ms/1000):
        filtered=closed_candles(cs,safety_seconds=15)
    assert [x.close_time_ms for x in filtered]==[now_ms-40_000,now_ms-100_000,now_ms-160_000]


def test_warmup_excludes_future_candles():
    candles=[candle(i) for i in range(39)]
    warmup,analysis=split_daily_candles_for_swing(closed_candles=candles,analysis_sessions=20,sma_period=20,strict=True)
    assert len(warmup)==19 and len(analysis)==20
    assert analysis[-1].open_time_ms==candles[-1].open_time_ms
    with pytest.raises(ValueError):
        split_daily_candles_for_swing(closed_candles=candles[:38],analysis_sessions=20,sma_period=20,strict=True)


def test_sizing_invalid_geometry_never_passes():
    with pytest.raises(NoValidSizingError):
        recommend_sizing(100,101,'HIGH',Settings(),side='LONG')
    with pytest.raises(NoValidSizingError):
        recommend_sizing(100,99,'HIGH',Settings(),side='SHORT')


def test_price_position_normalization():
    assert compute_position_pct(105,100,120)==pytest.approx(25.)
    assert compute_position_pct(100,100,100)==0.