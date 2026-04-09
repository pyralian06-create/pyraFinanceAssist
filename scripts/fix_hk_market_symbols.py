#!/usr/bin/env python3
"""
将 market_symbols 中港股 (STOCK_HK) 的短数字代码改为 5 位规范码（如 0700 -> 00700）。

不拉取东财接口，只改本地库。规则：
- symbol 为纯数字且长度 < 5 时，目标码为 symbol.zfill(5)；
- 若目标码已存在另一条记录，则删除当前短码行（保留已有 5 位行）；
- 若多条短码行映射到同一 5 位码，保留「原 symbol 位数最多」的一条并改为目标码，其余删除。

用法（在项目根目录）：
  python3 scripts/fix_hk_market_symbols.py
  python3 scripts/fix_hk_market_symbols.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="港股 symbol 短码改为 5 位")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印计划变更，不写库",
    )
    args = parser.parse_args()

    from app.models.database import SessionLocal
    from app.models.market_symbol import MarketSymbol

    db = SessionLocal()
    try:
        all_hk = (
            db.query(MarketSymbol)
            .filter(MarketSymbol.asset_type == "STOCK_HK")
            .all()
        )
        short = [r for r in all_hk if r.symbol.isdigit() and len(r.symbol) < 5]
        if not short:
            print("✅ 无需要迁移的港股短码记录（均为 5 位或非数字代码）")
            return 0

        by_target: dict[str, list[MarketSymbol]] = defaultdict(list)
        for r in short:
            by_target[r.symbol.zfill(5)].append(r)

        n_update = 0
        n_delete = 0
        plan: list[str] = []

        for target, group in sorted(by_target.items()):
            existing = (
                db.query(MarketSymbol)
                .filter(
                    MarketSymbol.asset_type == "STOCK_HK",
                    MarketSymbol.symbol == target,
                )
                .first()
            )

            if len(group) == 1:
                r = group[0]
                if existing is not None and existing.id != r.id:
                    plan.append(f"删除 {r.symbol!r}（已有 {target!r}）")
                    if not args.dry_run:
                        db.delete(r)
                    n_delete += 1
                else:
                    plan.append(f"{r.symbol!r} -> {target!r}")
                    if not args.dry_run:
                        r.symbol = target
                    n_update += 1
                continue

            group.sort(key=lambda x: len(x.symbol), reverse=True)
            keeper = group[0]
            if existing is not None and existing.id not in {x.id for x in group}:
                for r in group:
                    plan.append(f"删除 {r.symbol!r}（已有 {target!r}）")
                    if not args.dry_run:
                        db.delete(r)
                    n_delete += 1
            else:
                for r in group:
                    if r.id == keeper.id:
                        plan.append(f"{r.symbol!r} -> {target!r}（合并 {len(group)} 条）")
                        if not args.dry_run:
                            r.symbol = target
                        n_update += 1
                    else:
                        plan.append(f"删除重复 {r.symbol!r}")
                        if not args.dry_run:
                            db.delete(r)
                        n_delete += 1

        print(f"待处理短码行数: {len(short)}，涉及目标码种类: {len(by_target)}")
        for line in plan[:50]:
            print(f"  {line}")
        if len(plan) > 50:
            print(f"  … 共 {len(plan)} 条，仅显示前 50 条")

        if args.dry_run:
            print(f"[dry-run] 将更新约 {n_update} 条、删除约 {n_delete} 条（未写库）")
            return 0

        db.commit()
        print(f"✨ 完成：更新 {n_update} 条，删除 {n_delete} 条")
    except Exception as e:
        db.rollback()
        print(f"❌ 失败: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
