# WhyLowDps recovery data

This repository publishes verified Raidbots data snapshots used only to recover missing desktop game-data files. It is not an application-update channel and must never contain desktop update artifacts or version (`v*`) tags.

Every six hours, GitHub Actions fetches Raidbots `metadata.json` and each referenced file, packages them in an immutable timestamped ZIP archive, and uploads the archive before replacing the mutable `manifest.json` pointer on the `recovery-latest` release.

Desktop clients read the manifest from:

`https://github.com/JosephLteif/whylowdps-game-data/releases/download/recovery-latest/manifest.json`
