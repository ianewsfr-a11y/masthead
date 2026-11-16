# Horizon's preset sources

`horizon-presets.json` is Horizon's own preset library, copied unchanged from
`data/presets.json` of https://github.com/Thysrael/Horizon at the commit MastHead
pins (`323950050b079d054a009aa02198d89aae48e8da`). Horizon is under the MIT licence,
Copyright (c) 2026 Thysrael.

MastHead reads it with Horizon's own functions (`src/setup/presets.py`:
`load_presets` with the API turned off, then `match_sources`), as Horizon's setup
does in offline mode. MastHead never calls the online library at
`horizon1123.top`. Copy the file again when the pinned commit changes.
