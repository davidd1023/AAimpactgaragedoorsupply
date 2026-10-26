# Series 1200 door preview

A replacement for the 3D viewer on the product pages of
aaimpactgaragedoor.com. The site is WordPress on HostGator; this is an
ordinary self-contained bundle that needs no Odoo to run. It is kept in this
repository because the dev container is ephemeral, and because Odoo will serve
the test page on a real origin:

    /aa_door_preview/static/src/preview.html

Installing the module changes nothing in the database. It has no models, no
views and no data; the manifest exists only so the addons path serves the
folder.

## What the live site does today

Read off `davidaaigd.sirv.com/3d/` on 2026-10-26. The current viewer is Sirv's,
and it holds **one `.glb` per combination** of frame finish and glass colour:

| | Clear | White | Green | Bronze | Grey |
|---|---|---|---|---|---|
| **White** | 8.84 MB | — | — | — | — |
| **Black** | 8.84 MB | 8.84 MB | 8.84 MB | 8.84 MB | 8.84 MB |
| **Bronze** | 8.84 MB | — | 8.84 MB | 8.84 MB | 8.84 MB |
| **Wood** | — | — | 10.01 MB | 10.01 MB | 10.01 MB |

Thirteen files, about **118 MB**, and clicking a colour downloads a whole new
door.

**The seven dashes answer HTTP 404.** White frame with anything but Clear
glass, Bronze with White, and Wood with Clear or White cannot be shown on the
live site at all. Worth knowing before anything else is decided.

## Why one file is enough

Every one of those models is the **same single mesh** - one node, one mesh,
seven primitives, identical to within a few dozen bytes - and differs only in
what its materials are set to. Blender glTF exporter 4.1, no Draco, geometry
in the BIN chunk, and only the woodgrain files carry a texture (a 1024x1024
PNG, 1.17 MB, which is the whole of the 1.2 MB difference).

The materials are named by role, which is the part that makes this work:

| material | what it is | this viewer |
|---|---|---|
| `Silver` | hardware and track, metalness 0.98 | left alone |
| `Frame_white` / `Frane_Black` / `Frame_woodgrain` | the door's frame | **recoloured** |
| `Frame_bronze` | a piece that is dark (0.02 linear) in *every* one of his files, white and woodgrain included | left alone |
| `Glass_clear` / `_White` / `_green` / `_bronze` / `_grey` | the glazing, `KHR_materials_transmission` | **recoloured** |
| `Blue_Circle`, `White_Circle` | unidentified - a badge or a decal | left alone |

So: load one model, keep it, and set colours on its materials. One 8.8 MB
download instead of thirteen, every colour change instant, and all twenty
combinations render - the seven missing ones included.

## The numbers, as read out of his files

glTF `baseColorFactor` is **linear**, not sRGB, which is why `door_preview.js`
feeds these through `Color.fromArray` rather than a hex string. Nothing here
was invented or eyeballed.

### Frame finishes

| finish | base colour (linear) | metalness | roughness |
|---|---|---|---|
| White | 1, 1, 1 *(glTF default)* | 0.282 | 0.550 |
| Bronze | 0.0204, 0.0201, 0.0195 | 0.179 | 0.450 |
| Black | 0, 0, 0 | 0.282 | 0.095 |
| Wood | texture `albedoa` | 0.282 | 0.418 |

Bronze is **near black** - 0.02 linear is about `#282828` in sRGB. That is how
his files are set, and a dark anodized bronze really does read almost black,
so it is reproduced rather than corrected.

### Glass

| colour | base colour (linear) | transmission | roughness |
|---|---|---|---|
| Clear | 0.800, 0.800, 0.800 | 1.000 | 0.001 |
| White | 0.732, 0.800, 0.727 | 0.578 | 0.063 |
| Green | 0.195, 0.584, 0.301 | 0.578 | 0.063 |
| Bronze | 0.377, 0.090, 0.028 | 0.578 | 0.063 |
| Grey | 0.377, 0.377, 0.377 | 0.578 | 0.063 |

## Four things to settle with the owner

1. **Wood.** His Wood files put woodgrain on one frame primitive and leave the
   other **dark bronze**; the painted files colour both. This viewer makes the
   whole frame woodgrain, which is the consistent reading. If the dark piece is
   deliberate, `FRAME_RE` in `door_preview.js` is where to change it.
2. **`Frame_bronze`** is dark in every file, so it is treated as trim and left
   alone. If it is meant to take the finish, add it to `FRAME_RE`.
3. **`Blue_Circle` and `White_Circle`** - nobody has said what they are.
4. **`Frane_Black`** is a typo in the Black files. Harmless; `FRAME_RE` matches
   `fra[mn]e` so it is picked up either way. Worth fixing at the source if
   those files are ever re-exported.

## Putting it on WordPress

Four files go up, into one folder, by whoever has cPanel or FTP:

    door_preview.js      the viewer
    door_preview.css     its styles
    woodgrain.jpg        208 KB, re-encoded from the PNG inside Wood_Green.glb
    three.min.js         three.js r137.5
    GLTFLoader.js        its glTF loader

Then the embed, in a Custom HTML block or the page template:

```html
<link rel="stylesheet" href="/path/to/door_preview.css">
<div data-aa-door-preview
     data-model="https://davidaaigd.sirv.com/3d/White_Clear.glb"
     data-wood="/path/to/woodgrain.jpg"></div>
<script src="/path/to/three.min.js"></script>
<script src="/path/to/GLTFLoader.js"></script>
<script src="/path/to/door_preview.js"></script>
```

Any element with `data-aa-door-preview` is picked up on load. Nothing is
fetched from a CDN, so there is no third party that can break it; the only
external request is the model itself, from Sirv, which sends
`access-control-allow-origin: *`.

Everything is scoped under `.aadp` and sets its own box-sizing, font and
colours, because a WordPress theme knows nothing about it.

### Two improvements worth making later

- **Compress the mesh.** 8.8 MB of raw geometry for one door is heavy. Draco or
  meshopt should take it under 2 MB, which matters most on a phone.
- **Host the model next to the bundle.** It only needs Sirv because that is
  where it already is.
