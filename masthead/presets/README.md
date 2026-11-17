# Preset lists

`horizon-presets.json` is Horizon's own preset library, copied unchanged from
`data/presets.json` of https://github.com/Thysrael/Horizon at the commit MastHead
pins (`323950050b079d054a009aa02198d89aae48e8da`). Horizon is under the MIT licence,
Copyright (c) 2026 Thysrael.

MastHead reads it with Horizon's own functions (`src/setup/presets.py`:
`load_presets` with the API turned off, then `match_sources`), as Horizon's setup
does in offline mode. MastHead never calls the online library at
`horizon1123.top`. Copy the file again when the pinned commit changes.

The other files here are preset lists shipped with MastHead, in the same format. `flight-simulation.json` was built from the owner's virtual-flight sources (9 feeds, 2 subreddits); its Google News query and content extractors could not be carried, because Horizon's preset format has no place for them.

`finance.json` (added on 17 November 2026) goes with Horizon's built-in `finance-news` profile, since Horizon's own library has no finance theme: central banks (Federal Reserve, ECB, Bank of England, BIS speeches), the SEC, financial press in English and French (CNBC, MarketWatch, Bloomberg, Financial Times, The Economist, Investing.com, Le Monde, Le Figaro) and four subreddits. Every source answered `tools/check_preset_sources.py` that day. The Financial Times and The Economist are partly paywalled: the feed gives the headline and summary, the model may not read the whole article. Its keywords avoid the bare word "market", which Horizon's substring matching would find in "marketing".

`business-schools-europe.json` (added on 17 November 2026, asked by the owner): the business education press (Financial Times, Poets&Quants, Clear Admit), the news of two schools that publish a feed (Cambridge Judge, Rotterdam School of Management), French higher education press (Le Monde Campus, L'Etudiant), and Google News searches in English, French, German and Spanish. Most schools (INSEAD, HEC Paris, LBS, IESE, ESSEC, Bocconi...) publish no feed, or refuse automated readers; the Google News searches cover them. A Google News search is an ordinary RSS feed (`news.google.com/rss/search?q=...`); its links go through Google and its items carry only a headline. Every source answered `tools/check_preset_sources.py` that day.
