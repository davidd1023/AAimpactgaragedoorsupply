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

**One upload and one paste.** No FTP, no theme files, no plugin.

1. **Upload the texture.** Save `woodgrain.jpg` from this module and put it in
   the Sirv account beside the models, as `3d/woodgrain.jpg` - the same
   drag-and-drop that put the `.glb` files there. It is the only file that has
   to be hosted, and if it is missing everything still works; the Wood finish
   just comes out plain brown instead of grained.
2. **Paste the block.** `static/src/wordpress_embed.txt` is the whole viewer -
   stylesheet, markup and script in one block - ready for the **Elementor HTML
   widget** on the product page, in place of the current Sirv viewer. It is
   served as `text/plain` so it can be opened and copied straight out of a
   browser.

The same block goes on **all three series pages** (owner, 2026-10-26: "all 3
doors use the same model so we can use the same thing for all three"), and
because all three point at the same model URL a visitor downloads it once and
the browser serves the other two from cache.

Should a series offer less than the full range, narrow it per page without
touching any file:

```html
<div data-aa-door-preview
     data-model="https://davidaaigd.sirv.com/3d/White_Clear.glb"
     data-wood="https://davidaaigd.sirv.com/3d/woodgrain.jpg"
     data-frames="white,black"
     data-glasses="clear,grey"></div>
```

Any element with `data-aa-door-preview` is picked up on load. An empty or
unrecognised list offers everything rather than nothing.

### Do not edit the snippet

It is **generated** from `door_preview.css` and `door_preview.js`. Editing it
by hand is how it comes to differ from the viewer it was made from, and then a
fix made here stays broken on the website. Edit the module and run:

    python3 aa_door_preview/tools/build_embed.py

which rewrites `wordpress_embed.txt` and `embed_test.html` - a page that is
nothing but the snippet, so the exact thing about to be pasted can be looked
at working first.

### THE SNIPPET CARRIES NO `<script src>` TAGS, AND MUST NOT

The product pages are **Elementor**, and an Elementor HTML widget does not
have its markup parsed with the page: it is set as `innerHTML`, and setting
`innerHTML` **never executes an external script**. The inline script is picked
back out and re-run, which is why the first attempt showed the viewer's own
"could not load its renderer" message - its code was running, and three.js had
never arrived (owner, 2026-10-26).

So `door_preview.js` appends those library scripts itself, which does execute
them whoever injected the markup and whenever. `var THREE` is left null until
they are in, rather than read at parse time, because at parse time there is
nothing to read. The URLs can be overridden per page with `data-three` and
`data-gltf-loader`.

Adding script tags back to the snippet would restore the bug.

### What loads from where

Only two files come from outside: three.js and its glTF loader, pinned to
r137.5 on jsDelivr. They could be inlined too, but 600 KB in a page editor is
a bad afternoon, and they could be uploaded to Sirv except that whether a
media service returns `application/javascript` for a `.js` file is not worth
finding out on a live product page. An image it will certainly serve.

The model itself comes from Sirv, which sends `access-control-allow-origin: *`.

Everything is scoped under `.aadp` and sets its own box-sizing, font and
colours, because a WordPress theme knows nothing about it. A widget that is
re-rendered as it is edited will not mount twice; the element is marked
`data-aa-mounted` once it has one.

### Three test pages on the Odoo build

| page | what it proves |
|---|---|
| `static/src/preview.html` | the viewer, with the libraries served from this module |
| `static/src/embed_test.html` | the snippet itself, over the real CDN and the real texture URL |
| `static/src/elementor_test.html` | the snippet injected as `innerHTML` with its scripts re-run - **the way it failed**, so the fix is testable without pasting into a live page |

### Two improvements worth making later

- **Compress the mesh.** 8.8 MB of raw geometry for one door is heavy. Draco or
  meshopt should take it under 2 MB, which matters most on a phone.
- **Host the model next to the bundle.** It only needs Sirv because that is
  where it already is.
