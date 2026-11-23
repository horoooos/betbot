# Source-based fallback for paper forecasting

Enabled permanently by data/external_trial.json with permanent=true and fallback_only=true. Legacy dated configurations still expire. The external_trial storage key is retained for historical compatibility.
Only used when the regular value gate has no eligible main forecast. No bookmaker orders are placed.

- Current quoted price must exist for the exact modeled outcome, within 1.40–4.00.
- Dated public picks must match sport, division, event ID, kickoff and be observed before publication.
- Two distinct crowd-author records, or one structured editorial pick from a configured publisher.
- Recorded expert prices never become current prices. Model probabilities remain model probabilities.
- The fallback may admit negative baseline edge, without claiming confirmed value; normal pro.stake stays unchanged.
- Stake: 0.5% of the virtual bank. At most six open trial positions. No bold secondary pick or top-pick push.
- Each published source-based forecast saves immutable source references, model assessment, odds, stake and Telegram message ID.
- Outcomes use the existing results settlement; source_trial ledger waits for matching actual outcomes and tracks its own profit.
- CSV rows carry strategy=external_trial. Existing historical data and bankroll formulas are retained.
- Learned multi-source probabilities still require chronological validation. This experiment does not fake that validation.
- Forecasts and results stay out of the news-only VK and Dzen feeds.

Public cards use the normal match layout. Captions keep model probabilities labeled as model estimates and may show the count of external opinions; no temporary/test/experimental labels are emitted. Source references and selection provenance remain in the ledger and full analysis.
