# Contributing to MastHead

MastHead is an interface for [Horizon](https://github.com/Thysrael/Horizon): it shows and drives what Horizon already does, and adds no function to the engine. Read the first rule in `CLAUDE.md` before proposing a change to the code.

The easiest contribution is a **preset list**: ready-made sources for one theme.

## Preset lists

A preset list is a JSON file in Horizon's own preset format, the format of `data/presets.json` in Horizon's repository. Whoever installs MastHead finds its sources with **Search the presets**, when creating a domain or in the Sources step of the editor.

### Two ways to share a list

1. **As a file, today.**
   1. Open your domain in MastHead, step *Sources*, then *Share these sources as a preset list*.
   2. Give a theme and keywords, then download the file.
   3. Whoever receives it drops it in their `~/.masthead/presets/` folder. Nothing is sent anywhere.
2. **In this repository**, so that the list comes with MastHead:
   1. Add the file to `masthead/presets/`.
   2. Open a pull request.

   The maintainer reviews it; the automatic checks run on every pull request.

### What a list must hold

```json
{
  "domains": [
    {
      "id": "flight-simulation",
      "name": "Flight simulation",
      "keywords": ["flight simulator", "msfs", "x-plane", "simulation de vol"],
      "sources": [
        {
          "type": "rss",
          "description": "Flight simulation news site: add-ons, simulators, reviews",
          "tags": ["msfs", "press"],
          "config": { "name": "FSElite", "url": "https://fselite.net/feed/" }
        }
      ]
    }
  ]
}
```

| Field | Rule |
|---|---|
| `id` | Lowercase letters, digits and dashes. It is unique across the lists of this repository. |
| `name` | The theme, as it is shown in the search. |
| `keywords` | Lowercase words someone would type to find the theme, in any language. Horizon matches them as parts of words, so avoid very short ones (`ai` also matches "sailing"). |
| `sources[].type` | One of: `rss`, `github_repo`, `github_user`, `reddit_subreddit`, `reddit_user`, `telegram`, `hackernews`. |
| `sources[].config` | What identifies the source: `rss`: `name`, `url` (https); `github_repo`: `owner`, `repo`; `github_user` and `reddit_user`: `username`; `reddit_subreddit`: `subreddit`; `telegram`: `channel`. Optional: `category` (rss); `sort`, `fetch_limit`, `min_score` (subreddit); `fetch_limit` (telegram). |
| `sources[].description` | One line saying what the source is. Required in this repository. |
| `sources[].tags` | A few words, used by the search. |

A source appears only once in a list.

### Checks

`tests/test_preset_lists.py` runs on every pull request:

- every file is read as Horizon's setup would read it;
- every source can be built by Horizon;
- ids are unique, keywords and descriptions are present, feed addresses use https.

To check that the sources still answer (this reads every source, so it needs the network):

```bash
python tools/check_preset_sources.py
```

It runs Horizon's collector on each source over the last 7 days and lists what fails or published nothing. Run it before proposing a list. The maintainer runs it from time to time to remove dead feeds.

### What the maintainer looks at

- Sources that are public, about the theme, and still publishing.
- No tracking links, shorteners, or addresses that are not the source itself: a source is an address that Horizon will fetch on the user's computer.
- A list that duplicates another one is merged into it.

## Licence

MastHead is under the MIT licence (`LICENSE`). By proposing a change or a preset list, you agree that it is published under that licence. `masthead/presets/horizon-presets.json` is Horizon's own file, under Horizon's MIT licence (see `masthead/presets/README.md`).
