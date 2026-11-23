# Temporary source-based paper forecasting

Enabled for the fixed interval in data/external_trial.json (seven days), with automatic expiry.
Only used when the regular value gate has no eligible main forecast. No bookmaker orders are placed.

- Current quoted price must exist for the exact modeled outcome, within 1.40–4.00.
- Dated public picks must match sport, division, event ID, kickoff and be observed before publication.
- Two distinct crowd-author records, or one structured editorial pick from a configured publisher.
- Recorded expert prices never become current prices. Model probabilities remain model probabilities.
- The trial may admit negative baseline edge, explicitly labeled as unconfirmed; normal pro.stake stays unchanged.
- Stake: 0.5% of the virtual bank. At most six open trial positions. No bold secondary pick or top-pick push.
- Each published trial saves immutable source references, model assessment, odds, stake and Telegram message ID.
- Outcomes use the existing results settlement; source_trial ledger waits for matching actual outcomes and tracks its own profit.
- CSV rows carry strategy=external_trial. Existing historical data and bankroll formulas are retained.
- Learned multi-source probabilities still require chronological validation. This experiment does not fake that validation.
- Forecasts and results stay out of the news-only VK and Dzen feeds.
