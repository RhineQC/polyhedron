"""
Institutional Investment Portfolio Optimization — Comprehensive MIQCP

Long-only equity mandate implementing the full constraint taxonomy for a
multi-asset institutional portfolio manager.

Constraint categories covered
──────────────────────────────
 1  Budget equality       sum(w) = 1
 2  Long-only             w >= 0  (var lower bound)
 3  Box / holding bounds  BUY_IN_MIN <= w_i <= MAX_POSITION  (big-M)
 4  Cardinality cap       sum(z) <= K_MAX
 5  Cardinality floor     sum(z) >= K_MIN  (diversification)
 6  Buy-in threshold      w_i >= BUY_IN_MIN * z_i
 7  Turnover ℓ₁           sum(buy_i + sell_i) <= TURNOVER_LIMIT
 8  One-sided buy / sell  sum(buy) <= BUY_CAP ;  sum(sell) <= SELL_CAP
 9  Fixed tx cost         binary `traded_i` penalised in objective (MILP)
10  Variance cap (MIQCP)  w^T Σ w <= SIGMA_MAX²
11  CVaR(90%)             LP tail-risk cap via Rockafellar–Uryasev auxiliaries
12  Tracking error (QP)   (w-b)^T Σ (w-b) <= TE_MAX²
13  Sector exposure       sum_{i∈S}(w_i) <= SECTOR_CAP  per sector
14  Net beta              sum(β_i w_i) <= MAX_BETA
15  ESG floor             sum(ESG_i w_i) >= MIN_ESG
16  Return target         E[r]^T w >= RETURN_TARGET
17  Liquidity (ADV)       w_i <= adv_cap_i  per asset
18  Restricted list       w_i = 0  for banned tickers
19  Mutual exclusivity    z_JPM + z_GS <= 1  (single-bank mandate)

Objective
─────────
Maximize:  E[r]^T w  −  TRANSACTION_COST · sum(traded_i)
(expected return net of flat per-trade execution costs)
"""

import math

from polyhedron import Element, Model, maximize
from polyhedron.core.expression import QuadraticTerm
from polyhedron.modeling.element import Constraint
from polyhedron.modeling.uncertainty import cvar

# ─── Universe ─────────────────────────────────────────────────────────────────
#         ticker    E[R]    sector          β      ESG   ADV_cap  prev_w
UNIVERSE = [
    ("AAPL",  0.120, "Tech",        1.15,  0.72,  0.40,  0.20),
    ("MSFT",  0.110, "Tech",        1.05,  0.80,  0.35,  0.15),
    ("NVDA",  0.135, "Tech",        1.40,  0.55,  0.30,  0.00),
    ("JPM",   0.090, "Finance",     1.10,  0.60,  0.35,  0.25),
    ("GS",    0.095, "Finance",     1.20,  0.52,  0.25,  0.00),
    ("JNJ",   0.070, "Healthcare",  0.65,  0.85,  0.30,  0.20),
    ("UNH",   0.092, "Healthcare",  0.75,  0.82,  0.25,  0.00),
    ("XOM",   0.080, "Energy",      0.85,  0.35,  0.30,  0.10),
    ("CVX",   0.078, "Energy",      0.80,  0.38,  0.28,  0.00),  # restricted
    ("NEE",   0.060, "Utilities",   0.40,  0.78,  0.25,  0.10),
]
SECTORS = sorted({row[2] for row in UNIVERSE})

# Annual volatilities (σ_i) used to build the covariance matrix
VOLS = [0.28, 0.24, 0.40, 0.22, 0.26, 0.17, 0.20, 0.24, 0.22, 0.16]

# Equal-weight benchmark portfolio
N = len(UNIVERSE)
BENCHMARK = [1.0 / N] * N

# ─── Covariance matrix (sector-based correlation structure) ───────────────────
def _build_sigma(vols, universe):
    """σ_ij = ρ_ij · σ_i · σ_j with sector-aware correlations."""
    INTRA = {"Tech": 0.68, "Finance": 0.60, "Healthcare": 0.50,
             "Energy": 0.65, "Utilities": 1.00}
    CROSS = 0.28
    sectors = [row[2] for row in universe]
    return [
        [
            vols[i] ** 2 if i == j
            else (INTRA[sectors[i]] if sectors[i] == sectors[j] else CROSS)
                 * vols[i] * vols[j]
            for j in range(len(vols))
        ]
        for i in range(len(vols))
    ]

SIGMA = _build_sigma(VOLS, UNIVERSE)

# ─── Return scenarios for CVaR (stochastic return model) ─────────────────────
# Each entry: (probability, per-asset annual returns aligned to UNIVERSE order)
SCENARIOS = {
    "bull":   (0.20, [ 0.35,  0.30,  0.50,  0.20,  0.25,  0.15,  0.18,  0.22,  0.20,  0.12]),
    "normal": (0.35, [ 0.12,  0.11,  0.14,  0.09,  0.10,  0.07,  0.09,  0.08,  0.08,  0.06]),
    "soft":   (0.25, [-0.05, -0.03, -0.10, -0.04, -0.06,  0.01,  0.00, -0.02, -0.03,  0.02]),
    "stress": (0.12, [-0.25, -0.22, -0.38, -0.18, -0.24, -0.10, -0.14, -0.20, -0.18, -0.05]),
    "crash":  (0.08, [-0.40, -0.35, -0.55, -0.28, -0.35, -0.20, -0.25, -0.30, -0.28, -0.08]),
}

# ─── Constraint parameters ────────────────────────────────────────────────────
K_MAX            = 7      # max number of holdings (cardinality cap)
K_MIN            = 3      # min holdings (diversification floor)
MAX_POSITION     = 0.40   # box: maximum single-asset weight
BUY_IN_MIN       = 0.04   # minimum weight if selected (buy-in threshold)
TURNOVER_LIMIT   = 0.60   # max two-way portfolio turnover
BUY_CAP          = 0.40   # one-sided purchase limit
SELL_CAP         = 0.40   # one-sided sale limit
TRANSACTION_COST = 0.002  # 20 bps flat execution cost per traded asset
SECTOR_CAP       = 0.50   # maximum weight in any single sector
MAX_BETA         = 1.20   # maximum portfolio net beta
MIN_ESG          = 0.60   # minimum ESG-weighted score
RETURN_TARGET    = 0.085  # minimum expected annual return
CVaR_ALPHA       = 0.90   # CVaR confidence level (90% = expected loss in worst 10%)
CVaR_LIMIT       = 0.28   # maximum CVaR(90%) — 28% tail loss
SIGMA_MAX        = 0.23   # maximum annualized portfolio volatility (23%)
TE_MAX           = 0.20   # maximum tracking error vs equal-weight benchmark (20%)
RESTRICTED       = {"CVX"} # restricted / excluded tickers


# ─── Element ──────────────────────────────────────────────────────────────────
class Holding(Element):
    """One equity holding: fixed market data + four decision variables."""

    expected_return: float
    sector: str
    beta: float
    esg_score: float
    adv_cap: float       # liquidity cap (max weight from ADV constraint)
    prev_weight: float   # weight in the existing portfolio

    weight   = Model.ContinuousVar(min=0.0, max=MAX_POSITION)  # portfolio weight
    selected = Model.BinaryVar()                                # 1 if in portfolio
    buy      = Model.ContinuousVar(min=0.0, max=1.0)           # purchase leg
    sell     = Model.ContinuousVar(min=0.0, max=1.0)           # sale leg
    traded   = Model.BinaryVar()                               # 1 if any trade occurs

    @Constraint.auto
    def selection_link(self):
        """w_i ∈ [BUY_IN_MIN, MAX_POSITION] iff z_i = 1  (big-M)."""
        return [
            self.weight <= MAX_POSITION * self.selected,
            self.weight >= BUY_IN_MIN * self.selected,
        ]

    @Constraint.auto
    def turnover_decompose(self):
        """buy_i − sell_i = w_i − w_old_i  (ℓ₁ trade decomposition)."""
        return [self.buy - self.sell == self.weight - self.prev_weight]

    @Constraint.auto
    def trade_indicator(self):
        """Link traded binary to the buy/sell legs via big-M + min-size."""
        return [
            self.buy + self.sell <= self.traded,         # traded=0 forces no trade
            self.buy + self.sell >= BUY_IN_MIN * self.traded,  # min trade size
        ]

    @maximize(name="net_return")
    def objective(self):
        """Expected return minus flat transaction cost for each traded asset."""
        return self.expected_return * self.weight - TRANSACTION_COST * self.traded

# ─── Model ────────────────────────────────────────────────────────────────────
def main():
    model = Model("institutional_portfolio", solver="gurobi")

    holdings = [
        Holding(
            name=ticker,
            expected_return=ret,
            sector=sector,
            beta=beta,
            esg_score=esg,
            adv_cap=adv,
            prev_weight=prev,
        )
        for ticker, ret, sector, beta, esg, adv, prev in UNIVERSE
    ]
    model.add_elements(holdings)

    # ── 1. Budget equality ────────────────────────────────────────────────────
    model.constraints.append(sum(h.weight for h in holdings) == 1.0)

    # ── 2 + 3. Cardinality bounds ─────────────────────────────────────────────
    n_held = sum(h.selected for h in holdings)
    model.constraints.append(n_held <= K_MAX)
    model.constraints.append(n_held >= K_MIN)

    # ── 7 + 8. Turnover ℓ₁ and one-sided buy / sell limits ───────────────────
    model.constraints.append(sum(h.buy + h.sell for h in holdings) <= TURNOVER_LIMIT)
    model.constraints.append(sum(h.buy for h in holdings) <= BUY_CAP)
    model.constraints.append(sum(h.sell for h in holdings) <= SELL_CAP)

    # ── 10. Variance cap (quadratic constraint: w^T Σ w ≤ σ_max²) ────────────
    variance = sum(
        SIGMA[i][j] * QuadraticTerm(holdings[i].weight, holdings[j].weight)
        for i in range(N) for j in range(N)
    )
    model.constraints.append(variance <= SIGMA_MAX ** 2)

    # ── 11. CVaR(90%) cap via Rockafellar–Uryasev LP reformulation ───────────
    scenario_losses = {
        name: sum(-ret[i] * holdings[i].weight for i in range(N))
        for name, (_, ret) in SCENARIOS.items()
    }
    cvar_expr = cvar(
        model,
        scenario_losses,
        alpha=CVaR_ALPHA,
        probabilities={name: prob for name, (prob, _) in SCENARIOS.items()},
        name="portfolio_cvar",
    )
    model.constraints.append(cvar_expr <= CVaR_LIMIT)

    # ── 12. Tracking error (quadratic): (w−b)^T Σ (w−b) ≤ TE_MAX² ───────────
    te = sum(
        SIGMA[i][j]
        * (holdings[i].weight - BENCHMARK[i])
        * (holdings[j].weight - BENCHMARK[j])
        for i in range(N) for j in range(N)
    )
    model.constraints.append(te <= TE_MAX ** 2)

    # ── 13. Sector exposure caps ──────────────────────────────────────────────
    for sector in SECTORS:
        in_sector = [h for h in holdings if h.sector == sector]
        model.constraints.append(sum(h.weight for h in in_sector) <= SECTOR_CAP)

    # ── 14. Net portfolio beta ────────────────────────────────────────────────
    model.constraints.append(
        sum(h.beta * h.weight for h in holdings) <= MAX_BETA
    )

    # ── 15. ESG floor ─────────────────────────────────────────────────────────
    model.constraints.append(
        sum(h.esg_score * h.weight for h in holdings) >= MIN_ESG
    )

    # ── 16. Return target ─────────────────────────────────────────────────────
    model.constraints.append(
        sum(h.expected_return * h.weight for h in holdings) >= RETURN_TARGET
    )

    # ── 17. Per-asset liquidity cap (ADV fraction) ────────────────────────────
    for h in holdings:
        model.constraints.append(h.weight <= h.adv_cap)

    # ── 18. Restricted list ───────────────────────────────────────────────────
    for h in holdings:
        if h.name in RESTRICTED:
            model.constraints.append(h.weight == 0.0)
            model.constraints.append(h.selected == 0)

    # ── 19. Mutual exclusivity: cannot hold JPM and GS simultaneously ─────────
    jpm = next(h for h in holdings if h.name == "JPM")
    gs  = next(h for h in holdings if h.name == "GS")
    model.constraints.append(jpm.selected + gs.selected <= 1)

    # ─── Solve ────────────────────────────────────────────────────────────────
    solved = model.solve(time_limit=30, return_solved_model=True)
    status = getattr(solved.status, "value", str(solved.status))

    if status not in ("optimal", "feasible"):
        print(f"\nSolution status: {solved.status}")
        return solved, None

    # ─── Compute post-solve risk metrics ──────────────────────────────────────
    w = [solved.get_value(h.weight) for h in holdings]

    port_return = sum(UNIVERSE[i][1] * w[i] for i in range(N))
    port_beta   = sum(UNIVERSE[i][3] * w[i] for i in range(N))
    port_esg    = sum(UNIVERSE[i][4] * w[i] for i in range(N))
    port_var    = sum(SIGMA[i][j] * w[i] * w[j] for i in range(N) for j in range(N))
    port_vol    = math.sqrt(max(port_var, 0.0))
    te_realized = math.sqrt(max(
        sum(SIGMA[i][j] * (w[i] - BENCHMARK[i]) * (w[j] - BENCHMARK[j])
            for i in range(N) for j in range(N)),
        0.0,
    ))
    txn_cost    = sum(solved.get_value(h.traded) * TRANSACTION_COST for h in holdings)
    turnover    = sum(solved.get_value(h.buy) + solved.get_value(h.sell) for h in holdings)

    # CVaR in-sample (numerical, for reporting)
    scenario_p_losses = sorted(
        [(-sum(ret[i] * w[i] for i in range(N)), prob)
         for _, (prob, ret) in SCENARIOS.items()],
        reverse=True,
    )
    cum_p, cvar_num = 0.0, 0.0
    for loss, prob in scenario_p_losses:
        if cum_p >= (1 - CVaR_ALPHA):
            break
        take = min(prob, (1 - CVaR_ALPHA) - cum_p)
        cvar_num += loss * take / (1 - CVaR_ALPHA)
        cum_p += take

    active = [(h, w[i]) for i, h in enumerate(holdings) if w[i] > 1e-4]
    active.sort(key=lambda x: -x[1])

    # ─── Report ───────────────────────────────────────────────────────────────
    W = 72
    print(f"\n{'='*W}")
    print("INSTITUTIONAL PORTFOLIO OPTIMIZATION — RESULTS")
    print(f"{'='*W}")
    print(f"Status: {solved.status}")

    print(f"\n{'Ticker':<6} {'Weight':>7} {'Prev':>6} {'Sector':<12} {'E[R]':>5} "
          f"{'β':>5} {'ESG':>5} {'Trade':>8} {'Tx':>4}")
    print("-" * W)
    for h, wi in active:
        buy_v  = solved.get_value(h.buy)
        sell_v = solved.get_value(h.sell)
        trd    = int(round(solved.get_value(h.traded)))
        trade  = f"+{buy_v:.1%}" if buy_v > 1e-4 else (f"-{sell_v:.1%}" if sell_v > 1e-4 else "hold")
        flag   = "*" if h.prev_weight < 1e-4 else " "
        print(f"{flag}{h.name:<5} {wi:>7.2%} {h.prev_weight:>6.2%} {h.sector:<12} "
              f"{h.expected_return:>5.1%} {h.beta:>5.2f} {h.esg_score:>5.2f} "
              f"{trade:>8} {'yes' if trd else 'no':>4}")

    print(f"\n{'Sector':<14} {'Alloc':>8} {'Cap':>6}")
    print("-" * 30)
    for sector in SECTORS:
        alloc = sum(w[i] for i, row in enumerate(UNIVERSE) if row[2] == sector)
        if alloc > 1e-4:
            print(f"{sector:<14} {alloc:>8.2%} {SECTOR_CAP:>6.0%}")

    print(f"\n{'='*W}")
    print("RISK & MANDATE METRICS")
    print(f"{'='*W}")
    rows = [
        ("Portfolio E[R]",    f"{port_return:.2%}", f"≥ {RETURN_TARGET:.2%}"),
        ("Annualized vol",    f"{port_vol:.2%}",    f"≤ {SIGMA_MAX:.2%}"),
        ("CVaR(90%)",         f"{cvar_num:.2%}",    f"≤ {CVaR_LIMIT:.2%}"),
        ("Tracking error",    f"{te_realized:.2%}", f"≤ {TE_MAX:.2%}"),
        ("Net beta",          f"{port_beta:.2f}",   f"≤ {MAX_BETA:.2f}"),
        ("ESG score",         f"{port_esg:.2f}",    f"≥ {MIN_ESG:.2f}"),
        ("Active positions",  str(len(active)),      f"{K_MIN}–{K_MAX}"),
        ("Two-way turnover",  f"{turnover:.2%}",    f"≤ {TURNOVER_LIMIT:.0%}"),
        ("Transaction costs", f"{txn_cost:.2%}",    f"20 bps × traded"),
    ]
    for label, value, limit in rows:
        print(f"  {label:<22} {value:>8}   (limit: {limit})")

    print(f"\n  Restricted list  : {', '.join(RESTRICTED)}")
    print(f"  Mutual excl.     : JPM ⊕ GS  →  "
          f"{'JPM' if solved.get_value(jpm.selected) > 0.5 else 'GS'} selected")

    net_return = port_return - txn_cost
    print(f"\n  Net return after costs: {net_return:.2%}")

    return solved, net_return


if __name__ == "__main__":
    main()
