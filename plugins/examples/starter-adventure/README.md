# Lantern Harbor: creator starter

English | [简体中文](README_zh-CN.md)

An original **guided** example for the current DiceFrame contracts. It includes
two playable scenes (pier and beacon), an exclusive branch, a GM-only reference
ending and clue, a world template, an independent Book, and a two-location graph
map. It has no scripts, executable entrypoint, automated encounter or item reward.
Its declared dependency is `core:dnd2024` runtime contract 1, not an application
version. Story and data in this example use the repository's AGPL-3.0 license;
see the included LICENSE. No third-party story text or art is included.

From the repository root:

```sh
python scripts/validate_content_module.py plugins/examples/starter-adventure --json
python scripts/package_plugin.py plugins/examples/starter-adventure
python -m pytest tests/test_starter_adventure_conformance.py -q
```

Import the generated `.dfplugin` in Content packs, then enable it. Catalog mode
keeps installed sources available without automatically copying them into your
personal content. Select **Lantern Harbor** in the adventure library and start a
game with its explicit package source. The world and **Harbor Keeper Notes** are
separate resources; choose the Book for the game when you need its reference
material. The world supplies the harbor setting and default graph map.

The GM can review the secret ending; players receive the public projection.
The private transition is deliberately omitted from their choice list. A public
choice opens the public ending. Reference endings contain guidance for the GM;
they do not claim to automate a whole campaign.

To reuse the example, copy its directory and change the package ID and directory
together. Give the adventure and resources your own stable IDs; update declared
paths, map/world references and locale targets. Titles are display text and do
not create new identity. Validate the copied source **and the produced archive**
against the core revision you intend to support. Keep source rights and change
notes with your package. Do not replace the contents of a published version
silently, or bypass a bound-save update blocker.

The conformance test checks source/artifact validation, real install and game
creation, private projection, save/reload, export/reimport, bound-save protection,
and rejection of executable entrypoints, unsafe paths, missing runtimes, invalid
world relations and locale mechanics overrides. This evidence covers this
example and these operations, not every spell, combat rule or provider.
