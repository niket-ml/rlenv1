"""Fresh randomized execution order for the RC1.6 Case-2 sentinel."""

from pathlib import Path

from uc_bench.mmmvp_open_rc15_order import order_record

ORDER_PATH = Path("artifacts/mmmvp_open_rc16/sentinel_order.json")

__all__ = ["ORDER_PATH", "order_record"]
