# Further reading

The pages on this site explain what the app shows and why. The material below is where the design and the evidence live, for anyone who wants to go deeper or check the reasoning. All of it is in the project repository, [github.com/AlchemyGeek/Rotax9iSEIS](https://github.com/AlchemyGeek/Rotax9iSEIS).

## The research paper

*Rotax 91XiS Engine Data Analytics* — the paper that motivated the project and records what was learned from the first fifty flights of a Rotax 916iS. It sets out why FADEC engines need their own analytics (§§1–3), the flight-phase approach (§4), the limit checks (§5), cylinder balance (§6), the engine-computer alert classification (§7), and the stratification by weather conditions (§9).

→ `docs/ROTAX 91XiS Engine Data Analytics.md` in the repository.

## The specifications

Each part of the app is described in a numbered specification, kept up to date as the app changes. They are written for people building the app and use its internal vocabulary, but the sections on behaviour are readable by anyone.

| Spec | Subject | Read it for |
|---|---|---|
| 01 | Engine contract | Flight admission, phase detection, limit detection, CAS classification, the reference |
| 02 | Workspace | Log folders, skipped logs, export and import |
| 03 | User interface | Every page and what is on it |
| 07 | Flight chart | Channels and presets |
| 08 | Cylinder balance | The composite panel |
| 09 | Limit filters | Filters, their conditions, the change monitor |
| 10 | Analytics topics | Why these topics and not others; each topic's status per engine |
| 12 | Trends | The change page, shift, the recent window, pinning |
| 14 | Settings, Journal and rule editing | What each setting does; the Journal as a register |

→ `docs/specs/` in the repository.

## The Rotax Operators Manuals

The limits the app checks come from the Operators Manual for each engine model; the edition and revision used are shown under *Settings → Engine* and on the [limits page](om-limits.md). The manuals are Rotax's and are not included in the project; they are available from Rotax and your engine's documentation.

## Asking an assistant

Everything on this site is plain text in the repository under `docs/`. If you use an AI assistant, you can point it at the repository or paste the pages you are interested in and ask questions in your own words. The concept pages are written so that their opening *In brief* reads correctly out of context.
