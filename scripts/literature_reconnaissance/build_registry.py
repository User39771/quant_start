"""Build the curated literature registry from verified metadata and annotations."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs" / "literature_reconnaissance"
SOURCE = BASE / "raw_metadata" / "resolved_seed_papers.csv"


def key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


MANUAL = [
    ("A", "Replicating Anomalies", "Kewei Hou; Chen Xue; Lu Zhang", 2020, "Review of Financial Studies", "10.1093/rfs/hhy131", "https://doi.org/10.1093/rfs/hhy131", 1),
    ("A", "Does the Stock Market Overreact?", "Werner F. M. De Bondt; Richard Thaler", 1985, "The Journal of Finance", "10.1111/j.1540-6261.1985.tb05004.x", "https://doi.org/10.1111/j.1540-6261.1985.tb05004.x", 1),
    ("A", "The Other Side of Value: The Gross Profitability Premium", "Robert Novy-Marx", 2013, "Journal of Financial Economics", "10.1016/j.jfineco.2013.01.003", "https://doi.org/10.1016/j.jfineco.2013.01.003", 1),
    ("A", "What Characteristics Provide Independent Information About Average U.S. Stock Returns?", "Jeremiah Green; John R. M. Hand; X. Frank Zhang", 2017, "Review of Financial Studies", "10.1093/rfs/hhw109", "https://doi.org/10.1093/rfs/hhw109", 1),
    ("A", "Does Academic Research Destroy Stock Return Predictability?", "R. David McLean; Jeffrey Pontiff", 2016, "The Journal of Finance", "10.1111/jofi.12365", "https://doi.org/10.1111/jofi.12365", 1),
    ("B", "The Probability of Backtest Overfitting", "David H. Bailey; Jonathan M. Borwein; Marcos López de Prado; Qiji Jim Zhu", 2017, "Journal of Computational Finance", "10.21314/JCF.2016.322", "https://doi.org/10.21314/JCF.2016.322", 1),
    ("B", "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality", "David H. Bailey; Marcos López de Prado", 2014, "The Journal of Portfolio Management", "10.3905/jpm.2014.40.5.094", "https://doi.org/10.3905/jpm.2014.40.5.094", 1),
    ("B", "… and the Cross-Section of Expected Returns", "Campbell R. Harvey; Yan Liu; Heqing Zhu", 2016, "Review of Financial Studies", "10.1093/rfs/hhv059", "https://doi.org/10.1093/rfs/hhv059", 1),
    ("B", "Firm Characteristics and Expected Returns: A Model-Agnostic Approach", "Joachim Freyberger; Andreas Neuhierl; Michael Weber", 2020, "Review of Financial Studies", "10.1093/rfs/hhaa001", "https://doi.org/10.1093/rfs/hhaa001", 1),
    ("C", "Can Large Language Models Mine Interpretable Financial Factors More Effectively? A Neural-Symbolic Factor Mining Agent Model", "Zhiwei Li; Ran Song; Caihong Sun; Wei Xu; Zhengtao Yu; Ji-Rong Wen", 2024, "Findings of ACL 2024", "10.18653/v1/2024.findings-acl.233", "https://aclanthology.org/2024.findings-acl.233/", 1),
    ("C", "AlphaEvolve: A Learning Framework to Discover Novel Alphas in Quantitative Investment", "Can Cui; Wei Wang; Meihui Zhang; Gang Chen; Zhaojing Luo; Beng Chin Ooi", 2021, "ACM SIGMOD 2021", "10.1145/3448016.3457324", "https://doi.org/10.1145/3448016.3457324", 1),
    ("C", "Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning", "Shuo Yu; Hongyan Xue; Xiang Ao; Feiyang Pan; Jia He; Dandan Tu; Qing He", 2023, "ACM SIGKDD 2023", "10.1145/3580305.3599831", "https://doi.org/10.1145/3580305.3599831", 1),
    ("C", "RiskMiner: Discovering Formulaic Alphas via Risk Seeking Monte Carlo Tree Search", "Tao Ren; Ruihan Zhou; Jinyang Jiang; Jiafeng Liang; Qinghao Wang; Yijie Peng", 2024, "ACM ICAIF 2024", "10.1145/3677052.3698613", "https://doi.org/10.1145/3677052.3698613", 1),
    ("C", "AlphaAgent: LLM-Driven Alpha Mining with Regularized Exploration to Counteract Alpha Decay", "Ziyi Tang; Zechuan Chen; Jiarui Yang; Jiayao Mai; Yongsen Zheng; Keze Wang; Jinrui Chen; Liang Lin", 2025, "ACM SIGKDD 2025", "10.1145/3711896.3736838", "https://doi.org/10.1145/3711896.3736838", 1),
    ("C", "Navigating the Alpha Jungle: An LLM-Powered MCTS Framework for Formulaic Factor Mining", "Yu Shi; Yitong Duan; Jian Li", 2025, "arXiv", "arXiv:2505.11122v3", "https://arxiv.org/abs/2505.11122", 2),
    ("D", "Price, Trade Size, and Information in Securities Markets", "David Easley; Maureen O'Hara", 1987, "Journal of Financial Economics", "10.1016/0304-405X(87)90029-8", "https://doi.org/10.1016/0304-405X(87)90029-8", 1),
    ("D", "Trading Volume and Serial Correlation in Stock Returns", "John Y. Campbell; Sanford J. Grossman; Jiang Wang", 1993, "The Quarterly Journal of Economics", "10.2307/2118454", "https://doi.org/10.2307/2118454", 1),
    ("E", "Event Studies in Economics and Finance", "A. Craig MacKinlay", 1997, "Journal of Economic Literature", "JSTOR 2729691", "https://www.jstor.org/stable/2729691", 1),
    ("E", "Using Daily Stock Returns: The Case of Event Studies", "Stephen J. Brown; Jerold B. Warner", 1985, "Journal of Financial Economics", "10.1016/0304-405X(85)90042-X", "https://doi.org/10.1016/0304-405X(85)90042-X", 1),
    ("E", "Joint News, Attention Spillover, and Stock Returns", "Li Guo; Lin Peng; Yubo Tao; Jun Tu", 2025, "SSRN working paper", "SSRN 2927561", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2927561", 2),
    ("F", "A Unique T+1 Trading Rule in China: Theory and Evidence", "Ming Guo; Zhan Li; Zhiyong Tu", 2012, "Journal of Banking & Finance", "10.1016/j.jbankfin.2011.09.002", "https://doi.org/10.1016/j.jbankfin.2011.09.002", 1),
    ("F", "Does the T+1 Rule Really Reduce Speculation? Evidence from Chinese Stock Index ETF", "Xinyun Chen; Yan Liu; Tao Zeng", 2017, "Accounting & Finance", "10.1111/acfi.12330", "https://doi.org/10.1111/acfi.12330", 1),
    ("F", "T+1 Trading Mechanism Causes Negative Overnight Return", "Bing Zhang", 2020, "Economic Modelling", "10.1016/j.econmod.2019.10.013", "https://doi.org/10.1016/j.econmod.2019.10.013", 1),
    ("F", "Should Earnings Thresholds Be Used as Delisting Criteria in Stock Market?", "Guohua Jiang; Charles M. C. Lee; Heng Yue", 2008, "Journal of Accounting and Public Policy", "10.1016/j.jaccpubpol.2008.07.002", "https://doi.org/10.1016/j.jaccpubpol.2008.07.002", 1),
    ("F", "Statistical Properties and Pre-Hit Dynamics of Price Limit Hits in the Chinese Stock Markets", "Yu-Lei Wan; Wen-Jie Xie; Gao-Feng Gu; Zhi-Qiang Jiang; Wei Chen; Xiong Xiong; Wei Zhang; Wei-Xing Zhou", 2015, "PLOS ONE", "10.1371/journal.pone.0120312", "https://doi.org/10.1371/journal.pone.0120312", 1),
    ("F", "How Price Limit Affects the Market Efficiency in a Short-Sale Constrained Market? Evidence from a Quasi-Natural Experiment", "Haiqiang Chen; Ming Gu; Bo Ni", 2023, "Journal of Empirical Finance", "10.1016/j.jempfin.2023.05.003", "https://doi.org/10.1016/j.jempfin.2023.05.003", 1),
    ("F", "Limits of Arbitrage and Idiosyncratic Volatility: Evidence from China Stock Market", "Ming Gu; Wenjin Kang; Bu Xu", 2018, "Journal of Banking & Finance", "10.1016/j.jbankfin.2015.08.016", "https://doi.org/10.1016/j.jbankfin.2015.08.016", 1),
    ("F", "Survivorship Bias in Performance Studies", "Stephen J. Brown; William Goetzmann; Roger G. Ibbotson; Stephen A. Ross", 1992, "Review of Financial Studies", "10.1093/rfs/5.4.553", "https://doi.org/10.1093/rfs/5.4.553", 1),
    ("F", "Survivor Bias and Mutual Fund Performance", "Edwin J. Elton; Martin J. Gruber; Christopher R. Blake", 1996, "Review of Financial Studies", "10.1093/rfs/9.4.1097", "https://doi.org/10.1093/rfs/9.4.1097", 1),
    ("F", "The Overnight Return Puzzle and the T+1 Trading Rule in Chinese Stock Markets", "Kenan Qiao; Lammertjan Dam", 2020, "Journal of Financial Markets", "10.1016/j.finmar.2020.100534", "https://doi.org/10.1016/j.finmar.2020.100534", 1),
]


CORE = [
    ("A01", "The Cross-Section of Expected Stock Returns", True, "Which firm characteristics explain average stock returns?", "NYSE, AMEX, NASDAQ common stocks", "1963-1990", "monthly", "market beta, size, book-to-market, leverage, earnings-price", "cross-sectional stock returns", "cross-sectional regressions and portfolio sorts", "No modern train/validation/test split; historical inference sample", "CRSP/Compustat timing must be reconstructed by replicator", "not central", "average returns, regression slopes, portfolio spreads", "Author claim: size and book-to-market summarize much cross-sectional variation; beta alone does not.", "No prospective validation and no modern cost-aware long-only contract.", "The original paper predates today’s factor-zoo and multiple-testing standards.", "Foundation for separating rank predictiveness from implementable A-share long-only performance.", "Portfolio sorts and regressions answer different questions; publication-era evidence is not a Phase B test."),
    ("A02", "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency", False, "Do medium-horizon past winners continue to outperform past losers?", "NYSE and AMEX stocks", "1965-1989", "monthly", "past 3-12 month returns", "subsequent 3-12 month returns", "formation/holding-period portfolio sorts", "Overlapping historical portfolios; no locked prospective test", "CRSP histories; delisting treatment must be checked in replication", "not central in original abstract", "winner-minus-loser returns and post-holding behavior", "Author claim: intermediate-horizon return continuation is present and not explained by systematic risk.", "Long-run reversal and implementation frictions complicate direct use.", "The current theme pool is far smaller and has already produced negative MOM60 orientation.", "Historical momentum evidence motivates a hypothesis, not a direction guarantee in 56 stocks.", "Momentum horizon, skip period, and orientation must be preregistered."),
    ("A03", "A Taxonomy of Anomalies and Their Trading Costs", False, "Which anomaly returns survive realistic trading-cost estimates?", "U.S. equities", "historical anomaly samples", "monthly", "anomaly signals, turnover, liquidity and cost estimates", "net long-short anomaly returns", "standardized portfolio construction plus cost modeling", "Historical replication; no prospective final test", "requires time-appropriate universes and characteristics", "explicit", "gross/net returns, turnover, break-even costs", "Author claim: trading costs materially shrink the set and scale of implementable anomalies.", "Cost estimates and short-side feasibility are sample- and investor-specific.", "A-share T+1, limits and suspensions create different nonlinear implementation costs.", "Supports keeping turnover and cost treatment inside the factor contract.", "A statistically interesting spread can fail as an implementable long-only factor."),
    ("A04", "Replicating Anomalies", False, "How many published cross-sectional anomalies replicate under common procedures?", "U.S. equities", "1967-2016 (varies by anomaly)", "monthly", "452 published anomaly variables", "value- and equal-weighted anomaly returns", "uniform replication with higher significance hurdles", "Extended historical sample; not prospective", "requires survivorship-safe CRSP/Compustat construction", "considered through value weighting and implementability", "t-statistics, portfolio returns, replication rates", "Author claim: most anomalies fail, especially with value weights and higher multiple-testing hurdles.", "Results depend on harmonized implementation choices.", "Published specifications may omit researcher trials and data subtleties.", "Strong warning against interpreting one theme-pool success as general evidence.", "Replication quality and weighting matter as much as headline anomaly counts."),
    ("A05", "Empirical Asset Pricing via Machine Learning", True, "Can nonlinear ML improve cross-sectional return prediction out of sample?", "U.S. equities", "1957-2016", "monthly", "large characteristic set plus macro predictors", "one-month-ahead excess returns", "rolling train/validation/test comparison across ML models", "Explicit chronological training, validation and test samples", "CRSP/Compustat alignment described in study", "reported in portfolio evaluation", "out-of-sample R2, Sharpe, alpha, variable importance", "Author claim: nonlinear interactions and shrinkage improve out-of-sample prediction; trees and neural nets perform strongly.", "Economic interpretation and stability vary by model and period.", "Large U.S. panels and decades of data are unlike a 56-stock theme pool.", "Shows why an independent broad-market sandbox is needed for complex models.", "Model flexibility must be matched by sample size and honest validation."),
    ("B01", "A Reality Check for Data Snooping", True, "Is the best model found in a specification search truly superior to a benchmark?", "generic time-series applications", "methodological", "time series", "loss differentials across many candidate models", "best-model performance relative to benchmark", "bootstrap Reality Check for composite null", "Evaluation accounts for the searched family but not a prospective final test", "not market-data specific", "not market-data specific", "bootstrap p-value for superior predictive ability", "Author claim: the test controls inference when the same data support many model comparisons.", "Power may be weak when many poor alternatives are included.", "The candidate family and every tried variant must be logged; hidden human trials remain uncorrected.", "Direct basis for treating the experiment registry as a statistical input.", "Multiple testing is defined by all tried variants, not only reported winners."),
    ("B02", "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap", False, "Do technical rules retain evidence after accounting for the full search?", "Dow Jones Industrial Average", "1897-1996", "daily", "7,846 technical trading rules", "rule returns relative to benchmark", "bootstrap data-snooping correction", "Historical subperiod comparison, no modern prospective lockbox", "long historical index series", "limited relative to modern frictions", "bootstrap-adjusted significance and returns", "Author claim: apparent rule performance weakens materially after data-snooping correction and later data.", "Some early-sample results do not persist in later periods.", "Rule families and market structure differ from A-shares.", "Concrete example of why many thresholds cannot be judged one by one.", "A visually compelling rule can be a family-level false positive."),
    ("B03", "The Probability of Backtest Overfitting", True, "How can one estimate the chance that a selected backtest winner underperforms out of sample?", "generic investment simulations", "methodological/simulated examples", "strategy evaluation periods", "strategy-return matrix", "out-of-sample rank of in-sample winner", "combinatorially symmetric cross-validation (CSCV)", "Repeated symmetric train/test partitions; not a substitute for untouched final data", "depends on supplied strategy-return matrix", "captured only if present in returns", "PBO and logit of relative OOS rank", "Author claim: CSCV gives a model-free estimate of selection overfitting in backtests.", "Requires enough observations and a well-defined family of trials.", "Dependent, adaptively generated formulas complicate the effective trial family.", "Useful diagnostic only after the project records every candidate.", "PBO measures a search process, not an individual formula in isolation."),
    ("B04", "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality", True, "Is an observed Sharpe exceptional after trial count and non-normality?", "generic strategy returns", "methodological", "return-series frequency", "strategy return series", "Sharpe significance after selection", "probabilistic/deflated Sharpe calculation", "No train/test design; post-selection diagnostic", "depends on return inputs", "included through strategy returns", "DSR, observed Sharpe, skewness, kurtosis, number of trials", "Author claim: Sharpe evidence must be deflated for non-normal returns and multiple selections.", "Effective number and dependence of trials are hard to know.", "A tiny theme universe can make Sharpe estimation especially unstable.", "Possible secondary audit metric, not a replacement for Phase B.", "A high raw Sharpe can be unconvincing after accounting for the research path."),
    ("B05", "… and the Cross-Section of Expected Returns", True, "What statistical hurdle is appropriate after hundreds of factor searches?", "published cross-sectional asset-pricing studies", "1967-2012 literature census", "study-level", "study-level meta-analysis", "reported factor test statistics", "false discovery and multiple-testing thresholds", "meta-analysis; no single market split", "not applicable", "discussed as an economic screen", "adjusted t-statistic thresholds and false-discovery estimates", "Author claim: conventional t>1.96 is too low; a new factor generally needs a much higher hurdle.", "The true number and dependence of unpublished trials are unknown.", "One project’s adaptive iterations add local multiplicity beyond the published literature.", "Supports preregistration and conservative evidence grades.", "A factor’s t-statistic has meaning only relative to the search universe."),
    ("B06", "Survivorship Bias in Performance Studies", False, "How can conditioning on survival create apparent performance persistence?", "mutual fund/performance samples", "methodological with historical examples", "periodic returns", "survivor status and return histories", "measured performance persistence", "truncated-sample analysis and numerical examples", "No train/test split", "central: missing dead entities create the bias", "not central", "return-volatility relation and apparent persistence", "Author claim: survivorship truncation can create spurious predictability.", "Application is not a stock-factor backtest directly.", "A-share delistings, ST histories and changing theme membership create analogous risks.", "Justifies point-in-time universes and explicit dead/suspended securities.", "Universe construction is part of the hypothesis, not housekeeping."),
    ("C01", "AutoAlpha: an Efficient Hierarchical Evolutionary Algorithm for Mining Alpha Factors in Quantitative Investment", False, "Can hierarchical evolutionary search mine formulaic alphas efficiently?", "Chinese equities in reported experiments", "paper-specific historical split", "daily", "OHLCV and operator library", "future returns/rank correlation", "genetic programming with hierarchical search and root genes", "Historical train/test split reported; final untouched test needs independent review", "not established from reviewed abstract", "reported but implementation details require full text", "IC/RankIC and portfolio metrics", "Author claim: hierarchical evolution improves search efficiency and discovered-factor quality.", "Abstract does not establish full search-budget fairness.", "Evolution repeatedly reuses the same data and can overfit operators and parameters.", "Relevant baseline before any MCTS authorization.", "Genetic search is only meaningful against random search under the same budget."),
    ("C02", "AlphaEvolve: A Learning Framework to Discover Novel Alphas in Quantitative Investment", False, "Can learned mutation evolve a seed library into useful new formulas?", "real-world equity datasets", "paper-specific historical split", "daily", "seed alphas, OHLCV/operator library", "future returns and alpha performance", "learning-guided alpha evolution", "Historical evaluation; separation details require full text", "not established from reviewed abstract", "requires full-text check", "predictive and portfolio metrics", "Author claim: learned evolution discovers novel alphas more efficiently than baselines.", "Negative/null findings are not visible in the reviewed metadata.", "Novel syntax may still encode near-duplicate economics.", "Candidate baseline for formula canonicalization and budget fairness.", "Search policy, search space and evaluator must be separated conceptually."),
    ("C03", "Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning", True, "Can RL optimize an alpha collection for joint rather than individual usefulness?", "CSI 300 and CSI 500 in reported experiments", "paper-specific historical split", "daily", "OHLCV/operator library and existing factor pool", "future returns / ensemble RankIC", "risk-seeking policy-gradient construction of factor collections", "Historical train/test evaluation; no project-independent final lockbox", "requires full-text confirmation", "portfolio evaluation reported", "RankIC, ensemble performance, diversity", "Author claim: directly optimizing synergy improves a collection beyond selecting high-IC individual factors.", "Collection quality may not imply stable net long-only returns.", "The 56-stock theme cross-section is too small for a large search without a sandbox.", "Shows why marginal contribution and correlation belong in an Alpha Zoo.", "A factor is valuable for incremental information, not only standalone IC."),
    ("C04", "RiskMiner: Discovering Formulaic Alphas via Risk Seeking Monte Carlo Tree Search", True, "Can risk-seeking MCTS exploit formula-tree structure and collection synergy?", "two real-world stock sets", "paper-specific historical split", "daily", "OHLCV, operators, current alpha collection", "future cross-sectional returns", "reward-dense MDP plus risk-seeking MCTS", "Historical split; final lockbox and search reuse need scrutiny", "not established from reviewed abstract", "realistic trading claimed; details need full text", "IC/RankIC, collection metrics, backtest results", "Author claim: MCTS outperforms reported baselines under several metrics.", "Abstract supplies no negative results.", "Best-case/risk-seeking objectives may amplify selection bias without strict budget controls.", "Closest non-LLM MCTS comparator for the local paper.", "MCTS is an allocation rule for search budget, not an overfitting cure."),
    ("C05", "Can Large Language Models Mine Interpretable Financial Factors More Effectively? A Neural-Symbolic Factor Mining Agent Model", False, "Can an LLM combine symbolic interpretability with neural feature extraction?", "S&P 500", "training through 2021; exact full ranges require full text", "daily", "OHLCV, symbolic factors and neural features", "next-day stock returns", "FAMA with cross-sample selection and chain-of-experience", "Paper reports train/test datasets; independence of repeated prompting needs audit", "not established from abstract", "simulation reports portfolio metrics; execution assumptions need audit", "RankIC, RankICIR, annualized return, volatility, Sharpe", "Author claim: FAMA improves RankIC/RankICIR and reported investment metrics versus baselines.", "No negative findings in abstract.", "Very high reported Sharpe demands alignment, cost and leakage checks.", "Useful LLM-only/agent comparator, not evidence for immediate deployment.", "Interpretability claims need human-verifiable semantics and honest execution timing."),
    ("C06", "AlphaAgent: LLM-Driven Alpha Mining with Regularized Exploration to Counteract Alpha Decay", False, "Can structural, semantic and complexity regularization reduce alpha decay?", "CSI 500 and S&P 500", "approximately four years in reported study", "daily", "market fields, AST formula library, hypotheses", "future returns and decay-resistant performance", "LLM agent with AST similarity, hypothesis alignment and complexity controls", "Bull/bear and cross-market evaluations; final untouched test unclear from abstract", "not established from abstract", "reported simulations; details need full text", "decay, RankIC/returns and portfolio statistics", "Author claim: regularization improves originality and decay resistance across two markets.", "No explicit null result in abstract.", "Similarity and LLM semantic scores can become new tunable objectives.", "Supports canonicalization and complexity caps if automated search is later authorized.", "Regularization narrows search; it does not make repeated testing independent."),
    ("C07", "Navigating the Alpha Jungle: An LLM-Powered MCTS Framework for Formulaic Factor Mining", True, "Can LLM-guided MCTS mine diverse, interpretable formulaic alphas efficiently?", "CSI 300 and CSI 500", "2010-2023 with paper-defined IS/OOS partitions", "daily", "OHLC/VWAP/volume fields, operator library, seed formulas", "future cross-sectional returns and combined-model performance", "UCT MCTS, dimension-targeted LLM refinement, backtest reward and frequent-subtree avoidance", "Search uses training data; downstream test exists, but repeated OOS monitoring and parameter selection weaken lockbox status", "universe construction is reported but same-bar timing remains unclear", "turnover enters reward; full execution realism incomplete", "IC, RankIC, RankIR, turnover, diversity, AER, IR", "Author claim: MCTS, multidimensional feedback and FSA improve search efficiency, prediction, trading and interpretability.", "Some baselines win individual metrics; IS-OOS gap expands with depth.", "Three parameter tries per formula, max-value backup, LLM self-scored overfit risk and unclear signal lag all add risk.", "Local full-text anchor; learn the registry/reward design before considering implementation.", "Humans fix data, operators, seeds, reward and budget; AI proposes/refines formulas and allocates search."),
    ("D01", "The Relation between Price Changes and Trading Volume: A Survey", False, "What empirical and theoretical relations link price changes and volume?", "multiple markets reviewed", "literature through mid-1980s", "mixed", "price changes and volume", "contemporaneous and dynamic price-volume relations", "literature survey and organizing model", "not applicable", "varies by underlying study", "not central", "price-volume correlations", "Author claim: volume relates positively to absolute price changes and, in equities, often to signed changes.", "The survey does not validate any modern threshold signal.", "Microstructure, reporting and market regime differences limit direct transfer to A-shares.", "Mechanism map for converting volume narratives into falsifiable variables.", "Contemporaneous association is not a causal trading rule."),
    ("D02", "Trading Volume and Serial Correlation in Stock Returns", False, "Does volume condition short-horizon return autocorrelation?", "U.S. stock indexes and large stocks", "paper-specific daily samples", "daily", "returns and trading volume", "next-day return autocorrelation", "time-series regressions plus liquidity-trader model", "historical inference; no held-out test", "large-stock samples", "not central", "conditional autocorrelation coefficients", "Author claim: return autocorrelation declines with volume; high-volume declines imply higher expected returns in the model.", "Aggregate and large-stock evidence need not transfer cross-sectionally.", "Sign depends on whether volume reflects information or liquidity pressure.", "Supports explicit interaction terms rather than universal 'volume confirms price'.", "Volume can change the meaning of a return, but direction is state-dependent."),
    ("D03", "Price Momentum and Trading Volume", True, "Does past turnover identify different momentum life cycles?", "NYSE and AMEX equities", "1965-1995", "monthly", "past returns, turnover, firm characteristics", "future returns and earnings surprises", "double sorts and long-horizon event-time analysis", "Historical formation/holding samples; no prospective test", "CRSP/Compustat historical universe", "not central in abstract", "momentum spreads, reversals, earnings surprises", "Author claim: past volume predicts momentum magnitude/persistence; high-volume winners and losers reverse faster.", "Long-run results can be sensitive to microcaps and weighting.", "Turnover level is persistent and entangled with size, liquidity and attention.", "Best direct basis for a preregistered return×volume interaction.", "A volume filter changes the hypothesis; it is not just a liquidity screen."),
    ("D04", "The High-Volume Return Premium", False, "Does unusually high recent volume predict short-horizon returns?", "NYSE equities", "paper-specific historical sample", "weekly", "stock-specific abnormal trading volume", "subsequent returns", "event-time portfolio sorts around volume shocks", "Historical inference; no locked validation", "historical exchange sample", "not central", "return spreads after high/low volume events", "Author claim: stocks with unusually high volume tend to earn higher returns over the following month.", "Effect horizon is short and mechanism is attention/visibility rather than a universal rule.", "Price limits and retail attention may alter A-share shock behavior.", "Supports abnormal-volume—not raw-volume—definitions.", "Normalize volume to its own history before comparing stocks."),
    ("D05", "Dynamic Volume-Return Relation of Individual Stocks", True, "Can volume distinguish information-driven continuation from liquidity-driven reversal?", "NYSE/AMEX individual stocks", "1963-1998", "daily/weekly horizons", "returns, turnover and firm characteristics", "future return autocorrelation", "dynamic cross-sectional regressions motivated by trading model", "Historical sample; robustness but no prospective lockbox", "historical stock universe", "not central", "conditional return autocorrelation", "Author claim: volume-return dynamics vary with information asymmetry and liquidity trading.", "Mechanism proxies are imperfect.", "One observed volume spike cannot identify informed trading versus price pressure.", "Primary warning against attaching a single story to '放量'.", "The same mark can imply continuation or reversal under different mechanisms."),
    ("D06", "All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors", False, "Do attention-grabbing events affect investor purchase choices?", "U.S. brokerage and institutional trading data", "1991-1999", "daily", "news, extreme returns, abnormal volume and investor trades", "buying imbalance", "investor-level regressions and event comparisons", "Historical inference; no return-prediction lockbox", "investor samples are not a market universe", "not central", "buy-sell imbalance around attention events", "Author claim: individual investors are net buyers of attention-grabbing stocks, unlike institutions.", "Attention-induced buying is not itself a durable return premium.", "A-share retail composition and price limits may strengthen or distort the channel.", "Supports attention as one candidate mechanism for abnormal volume.", "Mechanism evidence about trades must not be rewritten as guaranteed return direction."),
    ("E01", "Event Studies in Economics and Finance", True, "How should event effects on firm value be measured and tested?", "general equity event studies", "methodological review", "daily and other horizons", "event dates, security and market returns", "abnormal and cumulative abnormal returns", "market-model event study, aggregation and inference", "Estimation and event windows separated; not train/test ML", "event timing must be point-in-time", "usually absent for short descriptive windows", "AR, CAR, test statistics", "Author claim: event studies can isolate market reactions when event definition, normal-return model and inference are disciplined.", "Power, clustering, event-date uncertainty and model choice can dominate results.", "Commercial-space events often overlap and contaminate the whole theme/industry.", "Defines the current event work as descriptive unless events and controls are preregistered.", "An event chart is not causal evidence without timing and counterfactual discipline."),
    ("E02", "Using Daily Stock Returns: The Case of Event Studies", False, "How well do common event-study tests behave with daily returns?", "U.S. securities in simulations", "historical daily return samples", "daily", "security and market returns with simulated events", "test size and power for abnormal returns", "large-scale simulation of event-study procedures", "random events/samples evaluate test specification", "historical universe construction", "not central", "empirical rejection rates and power", "Author claim: simple daily-return event methods can be well specified in many settings.", "Variance changes, clustering and non-random event selection remain concerns.", "A 56-stock theme can have correlated residuals and common event exposure.", "Basis for simulation-based calibration before interpreting CAR significance.", "Check test behavior under the project’s actual dependence, not textbook independence."),
    ("E03", "Allocating to Thematic Investments", False, "How can themes be treated alongside asset classes, sectors and styles?", "thematic investment portfolios", "methodological/application sample", "monthly/strategic horizon", "theme exposures, expected excess returns and traditional risk factors", "strategic portfolio allocation", "robust portfolio optimization with factor controls", "historical allocation exercise; no theme-membership lockbox", "theme definitions must be time-aware", "allocation context includes risk/cost tradeoffs", "risk, return and allocation weights", "Author claim: theme allocation should account jointly for thematic exposures and traditional factors.", "Theme measurement and expected returns remain uncertain.", "Concept-list membership can proxy industry/style exposure rather than pure theme exposure.", "Supports residualizing theme breadth against industry and size effects.", "A theme is an exposure definition, not evidence that its members share alpha."),
    ("F01", "Chinese Capital Market: An Empirical Overview", True, "What institutional and empirical features distinguish China’s capital market?", "Chinese A-share and related capital markets", "broad historical overview", "mixed", "market structure, ownership, trading and pricing evidence", "descriptive market outcomes", "survey and empirical synthesis", "not a predictive train/test design", "emphasizes institutional history", "discussed at market level", "market structure and return characteristics", "Author claim: China’s market combines rapid growth with distinctive institutions and investor composition.", "Survey findings do not specify a factor protocol.", "Rules change across boards and dates; implementation must be date-specific.", "Background for T+1, limits, suspensions, retail participation and state ownership.", "A-share constraints are part of the data-generating process."),
    ("F02", "A Unique T+1 Trading Rule in China: Theory and Evidence", False, "How does T+1 affect volume, volatility and trend chasing?", "Chinese B-shares with rule changes/evidence", "historical policy sample", "daily/intraday", "trading rule, volume, volatility and prices", "market quality outcomes", "dynamic manipulation model plus empirical test", "policy comparison rather than predictive split", "rule timing is central", "not a strategy-cost study", "volume, volatility and welfare implications", "Author claim: relative to T+0, T+1 reduces volume and volatility under model conditions; B-share evidence supports predictions.", "B-share setting and structural assumptions limit transfer.", "T+1 also changes feasible holding and same-day exit mechanics for any A-share signal.", "Requires next-day execution logic and rejects same-day round-trip assumptions.", "Trading rules can change both measured signal and attainable payoff."),
    ("F03", "How Price Limit Affects the Market Efficiency in a Short-Sale Constrained Market? Evidence from a Quasi-Natural Experiment", False, "How do price-limit width and short-sale constraints jointly affect price discovery?", "Chinese ChiNext/A-share natural experiment", "around the 2020 price-limit reform", "daily and event-time", "price-limit regime, shortability, orders, returns", "price efficiency and delayed discovery", "difference-in-differences and event study", "policy treatment/control design; not a factor train/test split", "board membership and rule dates are central", "not a trading strategy study", "price delay, reversal, volatility, institutional trading", "Author claim: wider limits improve efficiency, especially for shortable stocks; constrained stocks show more delayed discovery.", "Policy parallel-trend and market-regime assumptions matter.", "Limit-hit closes are not freely executable prices and can bias returns/turnover.", "Supports explicit limit-hit feasibility flags and delayed execution.", "A price limit is both information and a trading constraint; do not treat it as an ordinary return."),
]


FIELDS = [
    "paper_id", "cluster", "selection_status", "deep_read", "title", "authors",
    "year", "venue", "doi_or_stable_identifier", "source_url_or_location",
    "evidence_tier", "full_text_status", "research_question",
    "market_and_universe", "sample_period", "data_frequency", "input_variables",
    "target_variable", "method", "train_validation_test_design",
    "point_in_time_status", "transaction_cost_treatment", "main_metrics",
    "main_findings", "negative_or_null_findings",
    "limitations_reported_by_authors", "additional_limitations_identified",
    "relationship_to_current_project", "what_the_student_should_understand",
    "metadata_source",
]


def main() -> None:
    records: dict[str, dict] = {}
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if float(row["match_score"]) < 0.9 or not row["title"]:
                continue
            title_key = key(row["title"])
            venue = row["venue"]
            tier = 2 if "arxiv" in venue.lower() or "ssrn" in venue.lower() else 1
            records[title_key] = {
                "cluster": row["cluster"],
                "title": row["title"],
                "authors": row["authors"],
                "year": row["year"],
                "venue": venue,
                "doi_or_stable_identifier": (
                    row["doi"].replace("https://doi.org/", "")
                    or row["openalex_id"]
                    or "not_found"
                ),
                "source_url_or_location": row["landing_page_url"] or "not_found",
                "evidence_tier": tier,
                "metadata_source": "OpenAlex title-resolution; primary landing page",
            }

    for cluster, title, authors, year, venue, identifier, url, tier in MANUAL:
        records[key(title)] = {
            "cluster": cluster,
            "title": title,
            "authors": authors,
            "year": year,
            "venue": venue,
            "doi_or_stable_identifier": identifier,
            "source_url_or_location": url,
            "evidence_tier": tier,
            "metadata_source": "primary publisher/arXiv/SSRN page verified in web search",
        }

    core_by_key = {key(item[1]): item for item in CORE}
    rows: list[dict] = []
    candidate_index = 1
    for title_key, record in records.items():
        row = {field: "" for field in FIELDS}
        row.update(record)
        row["full_text_status"] = (
            "full_text_local"
            if title_key == key("Navigating the Alpha Jungle: An LLM-Powered MCTS Framework for Formulaic Factor Mining")
            else "abstract_only"
        )
        core = core_by_key.get(title_key)
        if core:
            (
                paper_id, _, deep, research_question, market, sample, frequency,
                inputs, target, method, split, pit, costs, metrics, findings,
                negative, extra_limits, relationship, student,
            ) = core
            row.update(
                {
                    "paper_id": paper_id,
                    "selection_status": "core",
                    "deep_read": str(deep).lower(),
                    "research_question": research_question,
                    "market_and_universe": market,
                    "sample_period": sample,
                    "data_frequency": frequency,
                    "input_variables": inputs,
                    "target_variable": target,
                    "method": method,
                    "train_validation_test_design": split,
                    "point_in_time_status": pit,
                    "transaction_cost_treatment": costs,
                    "main_metrics": metrics,
                    "main_findings": findings,
                    "negative_or_null_findings": negative,
                    "limitations_reported_by_authors": "Not separately available in the reviewed abstract/metadata; consult full text before relying on this field.",
                    "additional_limitations_identified": extra_limits,
                    "relationship_to_current_project": relationship,
                    "what_the_student_should_understand": student,
                }
            )
            if paper_id == "C07":
                row["limitations_reported_by_authors"] = (
                    "Novelty and complexity still trail human experts; the search space is bounded by "
                    "LLM knowledge, and very large-scale search may be difficult."
                )
        else:
            row["paper_id"] = f"CAND-{candidate_index:03d}"
            row["selection_status"] = "candidate"
            row["deep_read"] = "false"
            candidate_index += 1
        rows.append(row)

    # Correct issue-year metadata where early-online dates differ from the cited issue.
    issue_years = {
        key("Replicating Anomalies"): 2020,
        key("A Taxonomy of Anomalies and Their Trading Costs"): 2016,
        key("… and the Cross-Section of Expected Returns"): 2016,
        key("All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors"): 2008,
    }
    for row in rows:
        if key(row["title"]) in issue_years:
            row["year"] = issue_years[key(row["title"])]

    rows.sort(
        key=lambda row: (
            row["selection_status"] != "core",
            row["cluster"],
            row["paper_id"],
        )
    )
    with (BASE / "02_literature_registry.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    core_count = sum(row["selection_status"] == "core" for row in rows)
    deep_count = sum(row["deep_read"] == "true" for row in rows)
    print(f"registry={len(rows)} core={core_count} deep={deep_count}")


if __name__ == "__main__":
    main()
