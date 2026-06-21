from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .utils import parse_cache_date


@dataclass(frozen=True)
class BacktestConfig:
    factor_col: str = "composite_alpha_ic_weighted"
    top_n: int = 50
    rebalance_frequency: str = "monthly"
    buy_rank: int | None = None
    sell_rank: int | None = None
    keep_rank_threshold: int = 100
    max_turnover: float | None = None
    min_position_weight: float = 0.0
    dust_threshold: float = 0.0
    max_positions: int | None = None
    sell_priority: str = "worst_rank_first"
    weighting_method: str = "equal_weight"
    transaction_cost_rate: float = 0.002
    initial_nav: float = 1.0
    min_amount_20d: float = 50_000_000.0
    enable_liquidity_filter: bool = True
    enable_tradability_filter: bool = True


@dataclass(frozen=True)
class BacktestResult:
    nav: pd.DataFrame
    holdings: pd.DataFrame
    trades: pd.DataFrame
    metrics: pd.DataFrame
    warnings: pd.DataFrame


def compute_rebalance_period_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Compute stock returns from one rebalance month-end to the next."""
    frame = _normalize_panel(panel)
    if frame.empty:
        return frame
    month_end_dates = _month_end_dates(frame["date"])
    monthly = frame[frame["date"].isin(month_end_dates)].copy()
    if monthly.empty:
        return monthly
    next_date_map = {
        date: month_end_dates[index + 1] if index + 1 < len(month_end_dates) else pd.NaT
        for index, date in enumerate(month_end_dates)
    }
    monthly["next_rebalance_date"] = monthly["date"].map(next_date_map)

    if "adjusted_close" in monthly and monthly["adjusted_close"].notna().any():
        return _compute_adjusted_close_period_returns(monthly)
    if {"close", "adj_factor"}.issubset(monthly.columns):
        constructed = pd.to_numeric(monthly["close"], errors="coerce") * pd.to_numeric(
            monthly["adj_factor"], errors="coerce"
        )
        if constructed.notna().any():
            monthly = monthly.copy()
            monthly["adjusted_close"] = constructed
            return _compute_adjusted_close_period_returns(monthly, source="close_times_adj_factor_month_end")
    if "total_market_cap" in monthly and monthly["total_market_cap"].notna().any():
        return _compute_market_cap_period_returns(monthly)
    if "forward_return_20d" in monthly:
        result = monthly.copy()
        result["period_return"] = pd.to_numeric(result["forward_return_20d"], errors="coerce")
        result["period_return_source"] = "forward_return_20d_proxy"
        return result

    result = monthly.copy()
    result["period_return"] = np.nan
    result["period_return_source"] = "missing_return_source"
    return result


def compute_equal_weight_benchmark(
    cross_section: pd.DataFrame,
    *,
    min_amount_20d: float = 50_000_000.0,
    enable_liquidity_filter: bool = True,
    enable_tradability_filter: bool = True,
) -> tuple[float, int]:
    """Return tradable-universe equal-weight period return and valid stock count."""
    required = {"code", "next_rebalance_date", "period_return"}
    if cross_section.empty or not required.issubset(cross_section.columns):
        return np.nan, 0
    period_return = pd.to_numeric(cross_section["period_return"], errors="coerce")
    valid_code = cross_section["code"].astype(str).str.fullmatch(r"\d{6}").fillna(False)
    valid = cross_section["next_rebalance_date"].notna() & period_return.notna() & valid_code
    benchmark_pool, _stats = apply_buy_side_filters(
        cross_section.loc[valid],
        min_amount_20d=min_amount_20d,
        enable_liquidity_filter=enable_liquidity_filter,
        enable_tradability_filter=enable_tradability_filter,
    )
    valid_returns = pd.to_numeric(benchmark_pool["period_return"], errors="coerce").dropna()
    if valid_returns.empty:
        return np.nan, 0
    return float(valid_returns.mean()), int(valid_returns.shape[0])


def apply_buy_side_filters(
    frame: pd.DataFrame,
    *,
    min_amount_20d: float,
    enable_liquidity_filter: bool,
    enable_tradability_filter: bool,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Apply the rebalance-date liquidity and tradability rules used for buys."""
    candidate = frame.copy()
    liquidity_filtered_count = 0
    untradable_filtered_count = 0
    missing_liquidity_field = False
    missing_tradability_fields: list[str] = []
    tradability_candidate_count = 0

    if enable_liquidity_filter:
        if "amount_20d" in candidate:
            amount_20d = pd.to_numeric(candidate["amount_20d"], errors="coerce")
        else:
            amount_20d = pd.Series(np.nan, index=candidate.index)
            missing_liquidity_field = True
        liquidity_pass = amount_20d.notna() & amount_20d.ge(min_amount_20d)
        liquidity_filtered_count = int((~liquidity_pass).sum())
        candidate = candidate.loc[liquidity_pass].copy()

    if enable_tradability_filter:
        missing_tradability_fields = [column for column in ["amount", "high", "low"] if column not in candidate.columns]
        amount = (
            pd.to_numeric(candidate["amount"], errors="coerce")
            if "amount" in candidate
            else pd.Series(np.nan, index=candidate.index)
        )
        high = (
            pd.to_numeric(candidate["high"], errors="coerce")
            if "high" in candidate
            else pd.Series(np.nan, index=candidate.index)
        )
        low = (
            pd.to_numeric(candidate["low"], errors="coerce")
            if "low" in candidate
            else pd.Series(np.nan, index=candidate.index)
        )
        tradability_candidate_count = int(candidate.shape[0])
        # Buy-side only: no volume and one-price locked days are treated as not normally executable.
        tradability_pass = amount.notna() & high.notna() & low.notna() & amount.gt(0) & high.ne(low)
        untradable_filtered_count = int((~tradability_pass).sum())
        candidate = candidate.loc[tradability_pass].copy()

    return candidate, {
        "liquidity_filtered_count": liquidity_filtered_count,
        "untradable_filtered_count": untradable_filtered_count,
        "missing_liquidity_field": missing_liquidity_field,
        "missing_tradability_fields": missing_tradability_fields,
        "tradability_candidate_count": tradability_candidate_count,
    }


class MonthlyRebalanceBacktester:
    def __init__(self, config: BacktestConfig = BacktestConfig()):
        if config.top_n <= 0:
            raise ValueError("top_n must be positive")
        if config.rebalance_frequency != "monthly":
            raise ValueError("Only monthly rebalance_frequency is supported")
        if self._buy_rank(config) <= 0:
            raise ValueError("buy_rank must be positive")
        if config.sell_rank is None and config.keep_rank_threshold < config.top_n:
            raise ValueError("keep_rank_threshold must be greater than or equal to top_n")
        if self._sell_rank(config) < self._buy_rank(config):
            raise ValueError("sell_rank must be greater than or equal to buy_rank")
        if config.max_turnover is not None and not 0 <= config.max_turnover <= 2:
            raise ValueError("max_turnover must be between 0 and 2")
        if config.min_position_weight < 0:
            raise ValueError("min_position_weight must be non-negative")
        if config.dust_threshold < 0:
            raise ValueError("dust_threshold must be non-negative")
        if config.max_positions is not None and config.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if config.sell_priority not in {"worst_rank_first", "smallest_weight_first", "farthest_from_target_first"}:
            raise ValueError("sell_priority must be worst_rank_first, smallest_weight_first, or farthest_from_target_first")
        if config.weighting_method not in {"equal_weight", "rank_weight", "score_weight"}:
            raise ValueError("weighting_method must be equal_weight, rank_weight, or score_weight")
        if config.transaction_cost_rate < 0:
            raise ValueError("transaction_cost_rate must be non-negative")
        if config.initial_nav <= 0:
            raise ValueError("initial_nav must be positive")
        if config.min_amount_20d < 0:
            raise ValueError("min_amount_20d must be non-negative")
        self.config = config

    @staticmethod
    def _buy_rank(config: BacktestConfig) -> int:
        return int(config.buy_rank if config.buy_rank is not None else config.top_n)

    @staticmethod
    def _sell_rank(config: BacktestConfig) -> int:
        return int(config.sell_rank if config.sell_rank is not None else config.keep_rank_threshold)

    def run(self, factor_panel: pd.DataFrame) -> BacktestResult:
        period_panel = compute_rebalance_period_returns(factor_panel)
        warnings: list[dict[str, object]] = []
        nav_rows: list[dict[str, object]] = []
        holding_rows: list[dict[str, object]] = []
        trade_rows: list[dict[str, object]] = []
        previous_weights: dict[str, float] = {}
        nav = float(self.config.initial_nav)
        benchmark_nav = 1.0
        excess_nav = 1.0

        if period_panel.empty:
            warnings.append({"warning_type": "empty_factor_panel", "message": "No rows to backtest."})
            return BacktestResult(
                nav=_nav_frame(nav_rows),
                holdings=_holdings_frame(holding_rows, self.config.factor_col),
                trades=_trades_frame(trade_rows),
                metrics=_metrics_frame(nav_rows, self.config.initial_nav),
                warnings=_warnings_frame(warnings),
            )

        required = {"date", "code", self.config.factor_col, "next_rebalance_date", "period_return"}
        missing = sorted(required - set(period_panel.columns))
        if missing:
            warnings.append(
                {
                    "warning_type": "missing_required_columns",
                    "message": ",".join(missing),
                }
            )
            return BacktestResult(
                nav=_nav_frame(nav_rows),
                holdings=_holdings_frame(holding_rows, self.config.factor_col),
                trades=_trades_frame(trade_rows),
                metrics=_metrics_frame(nav_rows, self.config.initial_nav),
                warnings=_warnings_frame(warnings),
            )

        tradable = period_panel[period_panel["next_rebalance_date"].notna()].copy()
        if self.config.factor_col in tradable:
            tradable[self.config.factor_col] = pd.to_numeric(tradable[self.config.factor_col], errors="coerce")
        for rebalance_date, cross_section in tradable.groupby("date", sort=True):
            benchmark_return, benchmark_count = compute_equal_weight_benchmark(
                cross_section,
                min_amount_20d=self.config.min_amount_20d,
                enable_liquidity_filter=self.config.enable_liquidity_filter,
                enable_tradability_filter=self.config.enable_tradability_filter,
            )
            benchmark_factor_score = self._benchmark_factor_score(cross_section)
            valid = cross_section[cross_section[self.config.factor_col].notna()].copy()
            next_date = cross_section["next_rebalance_date"].iloc[0]
            if benchmark_count == 0:
                warnings.append(
                    {
                        "warning_type": "missing_benchmark_return",
                        "rebalance_date": _date_str(rebalance_date),
                        "next_rebalance_date": _date_str(next_date),
                        "benchmark_count": 0,
                        "message": "No valid tradable benchmark stocks; benchmark and excess NAV were not updated.",
                    }
                )
            if valid.empty:
                warnings.append(
                    {
                        "warning_type": "empty_factor_cross_section",
                        "rebalance_date": _date_str(rebalance_date),
                        "next_rebalance_date": _date_str(next_date),
                        "selected_count": 0,
                        "message": "Skipped rebalance and kept previous state because factor values were all missing.",
                    }
                )
                continue

            buyable, filter_stats = self._buyable_cross_section(valid, rebalance_date, next_date, warnings)
            liquidity_filtered_count = int(filter_stats["liquidity_filtered_count"])
            untradable_filtered_count = int(filter_stats["untradable_filtered_count"])
            buyable_count = int(buyable.shape[0])
            if buyable.empty:
                warnings.append(
                    {
                        "warning_type": "empty_buyable_cross_section",
                        "rebalance_date": _date_str(rebalance_date),
                        "next_rebalance_date": _date_str(next_date),
                        "liquidity_filtered_count": liquidity_filtered_count,
                        "untradable_filtered_count": untradable_filtered_count,
                        "message": "No stocks remained after buy-side liquidity and tradability filters.",
                    }
                )

            ranked_all = self._rank_cross_section(valid)
            ranked_buyable = self._rank_cross_section(buyable)
            desired = self._select_with_rank_buffer(ranked_buyable, previous_weights)
            desired_weights = self._desired_weights(desired)
            target_weights = self._apply_max_turnover(previous_weights, desired_weights, ranked_all)
            target_weights, sell_side_stats = self._apply_sell_side_constraints(
                previous_weights,
                target_weights,
                cross_section,
            )
            selected = self._rows_for_target_weights(ranked_all, target_weights)
            cash_weight = max(0.0, 1.0 - float(sum(target_weights.values())))
            selected_count = int(selected.shape[0])
            if selected_count < self.config.top_n:
                warnings.append(
                    {
                        "warning_type": "selected_count_below_top_n",
                        "rebalance_date": _date_str(rebalance_date),
                        "next_rebalance_date": _date_str(next_date),
                        "selected_count": selected_count,
                        "message": f"Only {selected_count} stocks passed factor, liquidity, and tradability filters.",
                    }
                )

            turnover, cost, trade_stats = self._append_trades(
                trade_rows,
                rebalance_date,
                previous_weights,
                target_weights,
            )
            trade_count = int(trade_stats["trade_count"])

            selected = selected.reset_index(drop=True).copy()
            missing_return = selected["period_return"].isna() if selected_count else pd.Series(dtype=bool)
            if selected_count and missing_return.any():
                warnings.append(
                    {
                        "warning_type": "missing_period_return",
                        "rebalance_date": _date_str(rebalance_date),
                        "next_rebalance_date": _date_str(next_date),
                        "count": int(missing_return.sum()),
                        "codes": ",".join(selected.loc[missing_return, "code"].astype(str).tolist()),
                        "message": "Missing stock period returns were kept as NaN in holdings and treated as zero contribution.",
                    }
                )

            selected["weight"] = selected["code"].astype(str).map(target_weights).fillna(0.0)
            # Missing individual returns are not dropped; zero contribution keeps NAV reproducible.
            selected["contribution"] = selected["weight"] * selected["period_return"].fillna(0.0)
            gross_return = float(selected["contribution"].sum())
            net_return = gross_return - cost
            nav *= 1.0 + net_return
            if pd.isna(benchmark_return):
                excess_return = np.nan
                # Keep relative NAVs flat when the benchmark leg is not observable.
                period_benchmark_nav = benchmark_nav
                period_excess_nav = excess_nav
            else:
                benchmark_nav *= 1.0 + benchmark_return
                excess_return = net_return - benchmark_return
                excess_nav *= 1.0 + excess_return
                period_benchmark_nav = benchmark_nav
                period_excess_nav = excess_nav
            return_source = _return_source(selected)
            position_stats = _position_stats(selected)
            portfolio_factor_score = _weighted_factor_score(selected, self.config.factor_col)
            active_factor_score = (
                portfolio_factor_score - benchmark_factor_score
                if pd.notna(portfolio_factor_score) and pd.notna(benchmark_factor_score)
                else np.nan
            )

            for item in selected.to_dict("records"):
                holding_rows.append(
                    {
                        "rebalance_date": _date_str(rebalance_date),
                        "next_rebalance_date": _date_str(next_date),
                        "code": item["code"],
                        "name": item.get("name", item["code"]),
                        self.config.factor_col: item[self.config.factor_col],
                        "rank": int(item["rank"]) if pd.notna(item.get("rank")) else None,
                        "weight": float(item["weight"]),
                        "period_return": item["period_return"],
                        "contribution": float(item["contribution"]),
                    }
                )

            nav_rows.append(
                {
                    "date": _date_str(next_date),
                    "rebalance_date": _date_str(rebalance_date),
                    "next_rebalance_date": _date_str(next_date),
                    "nav": nav,
                    "gross_return": gross_return,
                    "net_return": net_return,
                    "turnover": turnover,
                    "transaction_cost": cost,
                    "trade_count": trade_count,
                    "buy_count": trade_stats["buy_count"],
                    "sell_count": trade_stats["sell_count"],
                    "partial_sell_count": trade_stats["partial_sell_count"],
                    "attempted_sell_count": sell_side_stats["attempted_sell_count"],
                    "blocked_sell_count": sell_side_stats["blocked_sell_count"],
                    "blocked_sell_weight": sell_side_stats["blocked_sell_weight"],
                    "forced_hold_count": sell_side_stats["forced_hold_count"],
                    "forced_hold_weight": sell_side_stats["forced_hold_weight"],
                    "turnover_from_buys": trade_stats["turnover_from_buys"],
                    "turnover_from_sells": trade_stats["turnover_from_sells"],
                    "cash_weight": cash_weight,
                    "selected_count": selected_count,
                    "positions_below_5bp": position_stats["positions_below_5bp"],
                    "positions_below_10bp": position_stats["positions_below_10bp"],
                    "positions_below_20bp": position_stats["positions_below_20bp"],
                    "weight_below_10bp": position_stats["weight_below_10bp"],
                    "top10_weight": position_stats["top10_weight"],
                    "top20_weight": position_stats["top20_weight"],
                    "effective_number_of_positions": position_stats["effective_number_of_positions"],
                    "portfolio_factor_score": portfolio_factor_score,
                    "benchmark_factor_score": benchmark_factor_score,
                    "active_factor_score": active_factor_score,
                    "liquidity_filtered_count": liquidity_filtered_count,
                    "untradable_filtered_count": untradable_filtered_count,
                    "buyable_count": buyable_count,
                    "return_source": return_source,
                    "benchmark_return": benchmark_return,
                    "benchmark_count": benchmark_count,
                    "benchmark_nav": period_benchmark_nav,
                    "excess_return": excess_return,
                    "excess_nav": period_excess_nav,
                }
            )
            previous_weights = target_weights

        if not nav_rows and not any(warning["warning_type"] == "empty_factor_cross_section" for warning in warnings):
            warnings.append(
                {
                    "warning_type": "no_backtest_periods",
                    "message": "No rebalance date had a following rebalance date.",
                }
            )

        return BacktestResult(
            nav=_nav_frame(nav_rows),
            holdings=_holdings_frame(holding_rows, self.config.factor_col),
            trades=_trades_frame(trade_rows),
            metrics=_metrics_frame(nav_rows, self.config.initial_nav),
            warnings=_warnings_frame(warnings),
        )

    def _append_trades(
        self,
        trade_rows: list[dict[str, object]],
        rebalance_date: pd.Timestamp,
        previous_weights: dict[str, float],
        target_weights: dict[str, float],
    ) -> tuple[float, float, dict[str, float]]:
        codes = sorted(set(previous_weights) | set(target_weights))
        changes = []
        for code in codes:
            previous_weight = float(previous_weights.get(code, 0.0))
            target_weight = float(target_weights.get(code, 0.0))
            weight_change = target_weight - previous_weight
            abs_weight_change = abs(weight_change)
            changes.append((code, previous_weight, target_weight, weight_change, abs_weight_change))
        turnover = float(sum(item[4] for item in changes))
        cost = turnover * self.config.transaction_cost_rate
        for code, previous_weight, target_weight, weight_change, abs_weight_change in changes:
            if abs_weight_change <= 1e-12:
                continue
            trade_rows.append(
                {
                    "rebalance_date": _date_str(rebalance_date),
                    "code": code,
                    "previous_weight": previous_weight,
                    "target_weight": target_weight,
                    "weight_change": weight_change,
                    "abs_weight_change": abs_weight_change,
                    "transaction_cost_contribution": (
                        cost * abs_weight_change / turnover if turnover > 0 else 0.0
                    ),
                }
            )
        trade_stats = {
            "trade_count": float(sum(1 for item in changes if item[4] > 1e-12)),
            "buy_count": float(sum(1 for item in changes if item[3] > 1e-12)),
            "sell_count": float(sum(1 for item in changes if item[3] < -1e-12 and item[2] <= 1e-12)),
            "partial_sell_count": float(sum(1 for item in changes if item[3] < -1e-12 and item[2] > 1e-12)),
            "turnover_from_buys": float(sum(item[3] for item in changes if item[3] > 1e-12)),
            "turnover_from_sells": float(sum(abs(item[3]) for item in changes if item[3] < -1e-12)),
        }
        return turnover, cost, trade_stats

    def _buyable_cross_section(
        self,
        valid: pd.DataFrame,
        rebalance_date: pd.Timestamp,
        next_date: pd.Timestamp,
        warnings: list[dict[str, object]],
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        candidate, stats = apply_buy_side_filters(
            valid,
            min_amount_20d=self.config.min_amount_20d,
            enable_liquidity_filter=self.config.enable_liquidity_filter,
            enable_tradability_filter=self.config.enable_tradability_filter,
        )
        if stats["missing_liquidity_field"]:
            warnings.append(
                {
                    "warning_type": "missing_liquidity_fields",
                    "rebalance_date": _date_str(rebalance_date),
                    "next_rebalance_date": _date_str(next_date),
                    "count": int(valid.shape[0]),
                    "message": "amount_20d is missing; affected factor-valid stocks are treated as not buyable.",
                }
            )
        missing_fields = stats["missing_tradability_fields"]
        if missing_fields:
            warnings.append(
                {
                    "warning_type": "missing_tradability_fields",
                    "rebalance_date": _date_str(rebalance_date),
                    "next_rebalance_date": _date_str(next_date),
                    "count": int(stats["tradability_candidate_count"]),
                    "message": ",".join(missing_fields),
                }
            )

        return candidate, {
            "liquidity_filtered_count": int(stats["liquidity_filtered_count"]),
            "untradable_filtered_count": int(stats["untradable_filtered_count"]),
        }

    def _select_with_rank_buffer(
        self,
        ranked: pd.DataFrame,
        previous_weights: dict[str, float],
    ) -> pd.DataFrame:
        if ranked.empty:
            selected = ranked.copy()
            selected["rank"] = pd.Series(dtype="int64")
            return selected
        previous_codes = set(previous_weights)
        sell_rank = self._sell_rank(self.config)
        buy_rank = self._buy_rank(self.config)
        retain_mask = ranked["code"].astype(str).isin(previous_codes) & ranked["rank"].le(sell_rank)
        retained = ranked.loc[retain_mask].copy()
        remaining_slots = max(self.config.top_n - int(retained.shape[0]), 0)
        if remaining_slots:
            retained_codes = set(retained["code"].astype(str))
            fill_pool = ranked.loc[
                ranked["rank"].le(buy_rank) & ~ranked["code"].astype(str).isin(retained_codes)
            ]
            fill = fill_pool.head(remaining_slots)
            selected = pd.concat([retained, fill], ignore_index=True)
        else:
            selected = retained.head(self.config.top_n)
        return selected.sort_values(["rank", "code"]).reset_index(drop=True)

    def _rank_cross_section(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            result = frame.copy()
            result["rank"] = pd.Series(dtype="int64")
            return result
        ranked = frame.sort_values([self.config.factor_col, "code"], ascending=[False, True]).reset_index(drop=True)
        ranked["rank"] = range(1, int(ranked.shape[0]) + 1)
        return ranked

    def _desired_weights(self, selected: pd.DataFrame) -> dict[str, float]:
        if selected.empty:
            return {}
        codes = selected["code"].astype(str).tolist()
        if self.config.weighting_method == "equal_weight":
            weights = pd.Series(1.0, index=selected.index)
        elif self.config.weighting_method == "rank_weight":
            ranks = pd.to_numeric(selected["rank"], errors="coerce").replace(0, np.nan)
            weights = 1.0 / ranks
        else:
            scores = pd.to_numeric(selected[self.config.factor_col], errors="coerce")
            weights = scores - scores.min() + 1.0
        weights = pd.to_numeric(weights, errors="coerce").fillna(0.0).clip(lower=0.0)
        if float(weights.sum()) <= 1e-12:
            weights = pd.Series(1.0, index=selected.index)
        weights = weights / weights.sum()
        return {code: float(weight) for code, weight in zip(codes, weights, strict=True)}

    def _apply_max_turnover(
        self,
        previous_weights: dict[str, float],
        desired_weights: dict[str, float],
        ranked: pd.DataFrame,
    ) -> dict[str, float]:
        if not previous_weights:
            if (
                self.config.max_turnover is not None
                and self.config.min_position_weight > 0
                and self.config.max_turnover < 1.0
            ):
                scaled = {
                    code: weight * float(self.config.max_turnover)
                    for code, weight in desired_weights.items()
                }
                return self._enforce_position_constraints(scaled, previous_weights, desired_weights, ranked)
            return {code: weight for code, weight in desired_weights.items() if abs(weight) > 1e-12}
        codes = set(previous_weights) | set(desired_weights)
        raw_turnover = sum(abs(float(desired_weights.get(code, 0.0)) - float(previous_weights.get(code, 0.0))) for code in codes)
        if self.config.max_turnover is None or raw_turnover <= self.config.max_turnover or raw_turnover <= 1e-12:
            return self._enforce_position_constraints(desired_weights, previous_weights, desired_weights, ranked)
        scale = float(self.config.max_turnover) / float(raw_turnover)
        target = {}
        for code in codes:
            previous = float(previous_weights.get(code, 0.0))
            desired = float(desired_weights.get(code, 0.0))
            weight = previous + (desired - previous) * scale
            if abs(weight) > 1e-12:
                target[code] = weight
        return self._enforce_position_constraints(target, previous_weights, desired_weights, ranked)

    def _enforce_position_constraints(
        self,
        weights: dict[str, float],
        previous_weights: dict[str, float],
        desired_weights: dict[str, float],
        ranked: pd.DataFrame,
    ) -> dict[str, float]:
        target = {code: max(0.0, float(weight)) for code, weight in weights.items() if weight > 1e-12}
        if self.config.min_position_weight > 0:
            target = {
                code: weight
                for code, weight in target.items()
                if code in previous_weights or weight >= self.config.min_position_weight
            }
        if self.config.dust_threshold > 0:
            target = {code: weight for code, weight in target.items() if weight >= self.config.dust_threshold}
        if self.config.max_positions is not None and len(target) > self.config.max_positions:
            keep = self._rank_codes_for_position_cap(target, desired_weights, ranked)[: self.config.max_positions]
            target = {code: target[code] for code in keep}
        total = float(sum(target.values()))
        if total > 1e-12:
            return {code: weight / total for code, weight in target.items()}
        return {}

    def _rank_codes_for_position_cap(
        self,
        weights: dict[str, float],
        desired_weights: dict[str, float],
        ranked: pd.DataFrame,
    ) -> list[str]:
        rank_lookup = {}
        if {"code", "rank"}.issubset(ranked.columns):
            rank_lookup = dict(zip(ranked["code"].astype(str), pd.to_numeric(ranked["rank"], errors="coerce"), strict=False))
        codes = list(weights)
        if self.config.sell_priority == "smallest_weight_first":
            return sorted(codes, key=lambda code: (-weights[code], float(rank_lookup.get(code, 1e12)), code))
        if self.config.sell_priority == "farthest_from_target_first":
            return sorted(
                codes,
                key=lambda code: (
                    -abs(weights[code] - float(desired_weights.get(code, 0.0))),
                    float(rank_lookup.get(code, 1e12)),
                    code,
                ),
            )
        return sorted(codes, key=lambda code: (float(rank_lookup.get(code, 1e12)), -weights[code], code))

    def _apply_sell_side_constraints(
        self,
        previous_weights: dict[str, float],
        target_weights: dict[str, float],
        cross_section: pd.DataFrame,
    ) -> tuple[dict[str, float], dict[str, float]]:
        stats = {
            "attempted_sell_count": 0.0,
            "blocked_sell_count": 0.0,
            "blocked_sell_weight": 0.0,
            "forced_hold_count": 0.0,
            "forced_hold_weight": 0.0,
        }
        if not previous_weights:
            return target_weights, stats
        current_rows = {}
        if "code" in cross_section:
            current_rows = {
                str(row["code"]): row
                for row in cross_section.drop_duplicates("code", keep="last").to_dict("records")
            }
        attempted = [
            code
            for code, previous in previous_weights.items()
            if float(target_weights.get(code, 0.0)) < float(previous) - 1e-12
        ]
        stats["attempted_sell_count"] = float(len(attempted))
        blocked = []
        for code in attempted:
            row = current_rows.get(str(code))
            if row is not None and not self._sellable_on_rebalance(row):
                blocked.append(code)
        if not blocked:
            return target_weights, stats

        blocked_set = set(blocked)
        stats["blocked_sell_count"] = float(len(blocked))
        stats["blocked_sell_weight"] = float(
            sum(float(previous_weights[code]) - float(target_weights.get(code, 0.0)) for code in blocked)
        )
        stats["forced_hold_count"] = float(len(blocked))
        stats["forced_hold_weight"] = float(sum(float(previous_weights[code]) for code in blocked))

        forced = {code: float(previous_weights[code]) for code in blocked}
        remaining_capacity = max(0.0, 1.0 - float(sum(forced.values())))
        other = {
            code: max(0.0, float(weight))
            for code, weight in target_weights.items()
            if code not in blocked_set and float(weight) > 1e-12
        }
        other_total = float(sum(other.values()))
        if other_total > remaining_capacity and other_total > 1e-12:
            scale = remaining_capacity / other_total
            other = {code: weight * scale for code, weight in other.items() if weight * scale > 1e-12}
        combined = {**other, **forced}
        return combined, stats

    def _sellable_on_rebalance(self, row: dict[str, object]) -> bool:
        amount = _numeric_or_nan(row.get("amount"))
        if pd.notna(amount) and amount <= 0:
            return False
        volume = _numeric_or_nan(row.get("volume"))
        if pd.notna(volume) and volume <= 0:
            return False
        high = _numeric_or_nan(row.get("high"))
        low = _numeric_or_nan(row.get("low"))
        if pd.notna(high) and pd.notna(low) and high == low:
            return False
        for flag in ["paused", "is_paused", "suspension", "suspend"]:
            value = row.get(flag)
            if str(value).strip().lower() in {"1", "true", "yes", "y", "paused", "suspended"}:
                return False
        status = str(row.get("trading_status", "")).strip().lower()
        if status in {"停牌", "paused", "suspended", "halted"}:
            return False
        return True

    def _benchmark_factor_score(self, cross_section: pd.DataFrame) -> float:
        if self.config.factor_col not in cross_section:
            return np.nan
        required = {"code", "next_rebalance_date", "period_return"}
        if cross_section.empty or not required.issubset(cross_section.columns):
            return np.nan
        period_return = pd.to_numeric(cross_section["period_return"], errors="coerce")
        valid_code = cross_section["code"].astype(str).str.fullmatch(r"\d{6}").fillna(False)
        valid = cross_section["next_rebalance_date"].notna() & period_return.notna() & valid_code
        benchmark_pool, _stats = apply_buy_side_filters(
            cross_section.loc[valid],
            min_amount_20d=self.config.min_amount_20d,
            enable_liquidity_filter=self.config.enable_liquidity_filter,
            enable_tradability_filter=self.config.enable_tradability_filter,
        )
        scores = pd.to_numeric(benchmark_pool[self.config.factor_col], errors="coerce").dropna()
        return float(scores.mean()) if not scores.empty else np.nan

    def _rows_for_target_weights(self, ranked: pd.DataFrame, target_weights: dict[str, float]) -> pd.DataFrame:
        if not target_weights:
            selected = ranked.head(0).copy()
            selected["rank"] = pd.Series(dtype="int64")
            return selected
        selected = ranked[ranked["code"].astype(str).isin(target_weights)].copy()
        return selected.sort_values(["rank", "code"]).reset_index(drop=True)


def _normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    result = panel.copy()
    if result.empty or "date" not in result or "code" not in result:
        return pd.DataFrame()
    result["date"] = parse_cache_date(result["date"])
    result["code"] = result["code"].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(6)
    result = result.dropna(subset=["date", "code"]).copy()
    for column in [
        "cf_yield_neutral",
        "composite_alpha",
        "composite_alpha_ic_weighted",
        "reversal_20d_neutral",
        "volatility_20d_neutral",
        "total_market_cap",
        "adjusted_close",
        "adj_factor",
        "close",
        "forward_return_20d",
        "amount",
        "amount_20d",
        "volume",
        "high",
        "low",
        "reversal_20d",
        "volatility_20d",
    ]:
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.sort_values(["date", "code"]).reset_index(drop=True)


def _month_end_dates(dates: pd.Series) -> list[pd.Timestamp]:
    frame = pd.DataFrame({"date": parse_cache_date(dates).dropna()})
    if frame.empty:
        return []
    month_ends = frame.groupby(frame["date"].dt.to_period("M"))["date"].max()
    return [pd.Timestamp(value) for value in month_ends.sort_values()]


def _compute_market_cap_period_returns(monthly: pd.DataFrame) -> pd.DataFrame:
    lookup = monthly[["date", "code", "total_market_cap"]].rename(
        columns={"date": "next_rebalance_date", "total_market_cap": "next_total_market_cap"}
    )
    result = monthly.merge(lookup, on=["code", "next_rebalance_date"], how="left")
    current_cap = pd.to_numeric(result["total_market_cap"], errors="coerce").where(lambda x: x > 0)
    next_cap = pd.to_numeric(result["next_total_market_cap"], errors="coerce").where(lambda x: x > 0)
    result["period_return"] = next_cap / current_cap - 1.0
    result["period_return_source"] = "total_market_cap_month_end"
    return result


def _compute_adjusted_close_period_returns(
    monthly: pd.DataFrame,
    *,
    source: str = "adjusted_close_month_end",
) -> pd.DataFrame:
    lookup = monthly[["date", "code", "adjusted_close"]].rename(
        columns={"date": "next_rebalance_date", "adjusted_close": "next_adjusted_close"}
    )
    result = monthly.merge(lookup, on=["code", "next_rebalance_date"], how="left")
    current_price = pd.to_numeric(result["adjusted_close"], errors="coerce").where(lambda x: x > 0)
    next_price = pd.to_numeric(result["next_adjusted_close"], errors="coerce").where(lambda x: x > 0)
    result["period_return"] = next_price / current_price - 1.0
    result["period_return_source"] = source
    return result


def _return_source(selected: pd.DataFrame) -> str:
    if "period_return_source" not in selected:
        return "unknown"
    sources = selected["period_return_source"].dropna().astype(str).unique().tolist()
    if not sources:
        return "unknown"
    return sources[0] if len(sources) == 1 else "mixed"


def _position_stats(selected: pd.DataFrame) -> dict[str, float]:
    if selected.empty or "weight" not in selected:
        return {
            "positions_below_5bp": 0.0,
            "positions_below_10bp": 0.0,
            "positions_below_20bp": 0.0,
            "weight_below_10bp": 0.0,
            "top10_weight": 0.0,
            "top20_weight": 0.0,
            "effective_number_of_positions": np.nan,
        }
    weights = pd.to_numeric(selected["weight"], errors="coerce").fillna(0.0).clip(lower=0.0)
    sorted_weights = weights.sort_values(ascending=False)
    square_sum = float((weights**2).sum())
    return {
        "positions_below_5bp": float(weights.lt(0.0005).sum()),
        "positions_below_10bp": float(weights.lt(0.001).sum()),
        "positions_below_20bp": float(weights.lt(0.002).sum()),
        "weight_below_10bp": float(weights[weights.lt(0.001)].sum()),
        "top10_weight": float(sorted_weights.head(10).sum()),
        "top20_weight": float(sorted_weights.head(20).sum()),
        "effective_number_of_positions": float(1.0 / square_sum) if square_sum > 1e-12 else np.nan,
    }


def _weighted_factor_score(selected: pd.DataFrame, factor_col: str) -> float:
    if selected.empty or factor_col not in selected or "weight" not in selected:
        return np.nan
    scores = pd.to_numeric(selected[factor_col], errors="coerce")
    weights = pd.to_numeric(selected["weight"], errors="coerce")
    valid = scores.notna() & weights.notna()
    if not valid.any():
        return np.nan
    return float((scores[valid] * weights[valid]).sum())


def _numeric_or_nan(value: object) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if pd.notna(numeric) else np.nan


def _metrics_frame(nav_rows: list[dict[str, object]], initial_nav: float) -> pd.DataFrame:
    if not nav_rows:
        rows = [
            ("annualized_return", np.nan, "no_periods"),
            ("max_drawdown", np.nan, "no_periods"),
            ("sharpe_ratio", np.nan, "insufficient_sample"),
            ("annualized_turnover", np.nan, "no_periods"),
            ("annualized_excess_return", np.nan, "no_excess_periods"),
            ("excess_max_drawdown", np.nan, "no_excess_periods"),
            ("information_ratio", np.nan, "insufficient_sample"),
            ("average_liquidity_filtered_count", np.nan, "no_periods"),
            ("average_untradable_filtered_count", np.nan, "no_periods"),
            ("average_holding_count", np.nan, "no_periods"),
            ("median_holding_count", np.nan, "no_periods"),
            ("max_holding_count", np.nan, "no_periods"),
            ("min_holding_count", np.nan, "no_periods"),
            ("average_trade_count", np.nan, "no_periods"),
            ("average_buy_count", np.nan, "no_periods"),
            ("average_sell_count", np.nan, "no_periods"),
            ("average_partial_sell_count", np.nan, "no_periods"),
            ("average_attempted_sell_count", np.nan, "no_periods"),
            ("average_blocked_sell_count", np.nan, "no_periods"),
            ("average_blocked_sell_weight", np.nan, "no_periods"),
            ("average_forced_hold_count", np.nan, "no_periods"),
            ("average_forced_hold_weight", np.nan, "no_periods"),
            ("average_transaction_cost", np.nan, "no_periods"),
            ("average_positions_below_5bp", np.nan, "no_periods"),
            ("average_positions_below_10bp", np.nan, "no_periods"),
            ("average_positions_below_20bp", np.nan, "no_periods"),
            ("average_weight_below_10bp", np.nan, "no_periods"),
            ("average_top10_weight", np.nan, "no_periods"),
            ("average_top20_weight", np.nan, "no_periods"),
            ("average_effective_number_of_positions", np.nan, "no_periods"),
            ("turnover_from_buys", np.nan, "no_periods"),
            ("turnover_from_sells", np.nan, "no_periods"),
            ("average_portfolio_factor_score", np.nan, "no_periods"),
            ("average_benchmark_factor_score", np.nan, "no_periods"),
            ("average_active_factor_score", np.nan, "no_periods"),
        ]
        return pd.DataFrame(rows, columns=["metric", "value", "note"])

    nav = pd.DataFrame(nav_rows)
    periods = int(nav.shape[0])
    ending_nav = float(nav["nav"].iloc[-1])
    annualized_return = (ending_nav / initial_nav) ** (12 / periods) - 1.0
    cumulative_max = nav["nav"].cummax()
    max_drawdown = float((nav["nav"] / cumulative_max - 1.0).min())
    monthly_returns = pd.to_numeric(nav["net_return"], errors="coerce").dropna()
    if monthly_returns.shape[0] < 2:
        sharpe = np.nan
        sharpe_note = "insufficient_sample"
    else:
        std = monthly_returns.std(ddof=1)
        if pd.isna(std) or std <= 1e-12:
            sharpe = np.nan
            sharpe_note = "zero_std"
        else:
            sharpe = float(monthly_returns.mean() / std * np.sqrt(12))
            sharpe_note = ""
    annualized_turnover = float(pd.to_numeric(nav["turnover"], errors="coerce").mean() * 12)
    average_liquidity_filtered_count = float(pd.to_numeric(nav["liquidity_filtered_count"], errors="coerce").mean())
    average_untradable_filtered_count = float(pd.to_numeric(nav["untradable_filtered_count"], errors="coerce").mean())
    holding_count = pd.to_numeric(nav["selected_count"], errors="coerce")
    average_holding_count = float(holding_count.mean())
    median_holding_count = float(holding_count.median())
    max_holding_count = float(holding_count.max())
    min_holding_count = float(holding_count.min())
    average_trade_count = float(pd.to_numeric(nav.get("trade_count"), errors="coerce").mean())
    average_buy_count = float(pd.to_numeric(nav.get("buy_count"), errors="coerce").mean())
    average_sell_count = float(pd.to_numeric(nav.get("sell_count"), errors="coerce").mean())
    average_partial_sell_count = float(pd.to_numeric(nav.get("partial_sell_count"), errors="coerce").mean())
    average_attempted_sell_count = float(pd.to_numeric(nav.get("attempted_sell_count"), errors="coerce").mean())
    average_blocked_sell_count = float(pd.to_numeric(nav.get("blocked_sell_count"), errors="coerce").mean())
    average_blocked_sell_weight = float(pd.to_numeric(nav.get("blocked_sell_weight"), errors="coerce").mean())
    average_forced_hold_count = float(pd.to_numeric(nav.get("forced_hold_count"), errors="coerce").mean())
    average_forced_hold_weight = float(pd.to_numeric(nav.get("forced_hold_weight"), errors="coerce").mean())
    average_transaction_cost = float(pd.to_numeric(nav["transaction_cost"], errors="coerce").mean())
    average_positions_below_5bp = float(pd.to_numeric(nav.get("positions_below_5bp"), errors="coerce").mean())
    average_positions_below_10bp = float(pd.to_numeric(nav.get("positions_below_10bp"), errors="coerce").mean())
    average_positions_below_20bp = float(pd.to_numeric(nav.get("positions_below_20bp"), errors="coerce").mean())
    average_weight_below_10bp = float(pd.to_numeric(nav.get("weight_below_10bp"), errors="coerce").mean())
    average_top10_weight = float(pd.to_numeric(nav.get("top10_weight"), errors="coerce").mean())
    average_top20_weight = float(pd.to_numeric(nav.get("top20_weight"), errors="coerce").mean())
    average_effective_number = float(pd.to_numeric(nav.get("effective_number_of_positions"), errors="coerce").mean())
    turnover_from_buys = float(pd.to_numeric(nav.get("turnover_from_buys"), errors="coerce").mean() * 12)
    turnover_from_sells = float(pd.to_numeric(nav.get("turnover_from_sells"), errors="coerce").mean() * 12)
    average_portfolio_factor_score = float(pd.to_numeric(nav.get("portfolio_factor_score"), errors="coerce").mean())
    average_benchmark_factor_score = float(pd.to_numeric(nav.get("benchmark_factor_score"), errors="coerce").mean())
    average_active_factor_score = float(pd.to_numeric(nav.get("active_factor_score"), errors="coerce").mean())
    excess_returns = pd.to_numeric(nav.get("excess_return"), errors="coerce").dropna()
    if excess_returns.empty:
        annualized_excess_return = np.nan
        annualized_excess_note = "no_excess_periods"
        excess_max_drawdown = np.nan
        excess_drawdown_note = "no_excess_periods"
    else:
        ending_excess_nav = float(pd.to_numeric(nav["excess_nav"], errors="coerce").dropna().iloc[-1])
        annualized_excess_return = (ending_excess_nav / 1.0) ** (12 / int(excess_returns.shape[0])) - 1.0
        annualized_excess_note = ""
        valid_excess_nav = pd.to_numeric(nav.loc[nav["excess_return"].notna(), "excess_nav"], errors="coerce").dropna()
        if valid_excess_nav.empty:
            excess_max_drawdown = np.nan
            excess_drawdown_note = "no_excess_periods"
        else:
            cumulative_max_excess = valid_excess_nav.cummax()
            excess_max_drawdown = float((valid_excess_nav / cumulative_max_excess - 1.0).min())
            excess_drawdown_note = ""
    if excess_returns.shape[0] < 2:
        information_ratio = np.nan
        information_ratio_note = "insufficient_sample"
    else:
        excess_std = excess_returns.std(ddof=1)
        if pd.isna(excess_std) or excess_std <= 1e-12:
            information_ratio = np.nan
            information_ratio_note = "zero_std"
        else:
            information_ratio = float(excess_returns.mean() / excess_std * np.sqrt(12))
            information_ratio_note = ""
    rows = [
        ("annualized_return", annualized_return, ""),
        ("max_drawdown", max_drawdown, ""),
        ("sharpe_ratio", sharpe, sharpe_note),
        ("annualized_turnover", annualized_turnover, ""),
        ("annualized_excess_return", annualized_excess_return, annualized_excess_note),
        ("excess_max_drawdown", excess_max_drawdown, excess_drawdown_note),
        ("information_ratio", information_ratio, information_ratio_note),
        ("average_liquidity_filtered_count", average_liquidity_filtered_count, ""),
        ("average_untradable_filtered_count", average_untradable_filtered_count, ""),
        ("average_holding_count", average_holding_count, ""),
        ("median_holding_count", median_holding_count, ""),
        ("max_holding_count", max_holding_count, ""),
        ("min_holding_count", min_holding_count, ""),
        ("average_trade_count", average_trade_count, ""),
        ("average_buy_count", average_buy_count, ""),
        ("average_sell_count", average_sell_count, ""),
        ("average_partial_sell_count", average_partial_sell_count, ""),
        ("average_attempted_sell_count", average_attempted_sell_count, ""),
        ("average_blocked_sell_count", average_blocked_sell_count, ""),
        ("average_blocked_sell_weight", average_blocked_sell_weight, ""),
        ("average_forced_hold_count", average_forced_hold_count, ""),
        ("average_forced_hold_weight", average_forced_hold_weight, ""),
        ("average_transaction_cost", average_transaction_cost, ""),
        ("average_positions_below_5bp", average_positions_below_5bp, ""),
        ("average_positions_below_10bp", average_positions_below_10bp, ""),
        ("average_positions_below_20bp", average_positions_below_20bp, ""),
        ("average_weight_below_10bp", average_weight_below_10bp, ""),
        ("average_top10_weight", average_top10_weight, ""),
        ("average_top20_weight", average_top20_weight, ""),
        ("average_effective_number_of_positions", average_effective_number, ""),
        ("turnover_from_buys", turnover_from_buys, ""),
        ("turnover_from_sells", turnover_from_sells, ""),
        ("average_portfolio_factor_score", average_portfolio_factor_score, ""),
        ("average_benchmark_factor_score", average_benchmark_factor_score, ""),
        ("average_active_factor_score", average_active_factor_score, ""),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def _nav_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "date",
        "rebalance_date",
        "next_rebalance_date",
        "nav",
        "gross_return",
        "net_return",
        "turnover",
        "transaction_cost",
        "trade_count",
        "buy_count",
        "sell_count",
        "partial_sell_count",
        "attempted_sell_count",
        "blocked_sell_count",
        "blocked_sell_weight",
        "forced_hold_count",
        "forced_hold_weight",
        "turnover_from_buys",
        "turnover_from_sells",
        "cash_weight",
        "selected_count",
        "positions_below_5bp",
        "positions_below_10bp",
        "positions_below_20bp",
        "weight_below_10bp",
        "top10_weight",
        "top20_weight",
        "effective_number_of_positions",
        "portfolio_factor_score",
        "benchmark_factor_score",
        "active_factor_score",
        "liquidity_filtered_count",
        "untradable_filtered_count",
        "buyable_count",
        "return_source",
        "benchmark_return",
        "benchmark_count",
        "benchmark_nav",
        "excess_return",
        "excess_nav",
    ]
    return pd.DataFrame(rows, columns=columns)


def _holdings_frame(rows: list[dict[str, object]], factor_col: str = "cf_yield_neutral") -> pd.DataFrame:
    columns = [
        "rebalance_date",
        "next_rebalance_date",
        "code",
        "name",
        factor_col,
        "rank",
        "weight",
        "period_return",
        "contribution",
    ]
    return pd.DataFrame(rows, columns=columns)


def _trades_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "rebalance_date",
        "code",
        "previous_weight",
        "target_weight",
        "weight_change",
        "abs_weight_change",
        "transaction_cost_contribution",
    ]
    return pd.DataFrame(rows, columns=columns)


def _warnings_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["warning_type", "rebalance_date", "next_rebalance_date", "message"])
    return pd.DataFrame(rows)


def _date_str(value: object) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()
