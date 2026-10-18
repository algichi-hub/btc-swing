-- F5 Preview prerequisite: UTC millisecond candle timestamps exceed INT32.
-- Non-destructive widening; apply with privileged migration owner before enabling
-- the cloud worker. No changes to the V4 trading algorithm or trade history.
ALTER TABLE public.trade_signals
  ALTER COLUMN last_processed_candle_close_ms TYPE BIGINT;
