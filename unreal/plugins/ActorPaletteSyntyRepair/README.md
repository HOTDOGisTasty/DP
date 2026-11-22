# Actor Palette Synty Repair

Editor-only one-time migration for this project.

On startup it replaces the stale Actor Palette map reference
`/Game/PolygonWar/Maps/Overview.Overview` with
`/Game/Synty/PolygonWar/Maps/Overview.Overview` in Unreal's private
Actor Palette settings. If a replacement happened, Actor Palette tab 1 is
opened once. Subsequent startups make no change.

No level, actor, or runtime data is modified.
