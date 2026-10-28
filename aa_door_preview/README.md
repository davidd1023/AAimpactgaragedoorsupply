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
all twenty of them, 8.84 MB each for the painted ones and 10.01 MB for the
woodgrain, about **180 MB** in all. Clicking a colour downloads a whole new
door.

**A CORRECTION.** This file first said seven of those combinations were
missing and answered 404. They were not. The names are inconsistently cased -
`White_Clear.glb` but `White_green.glb`, `Wood_Grey.glb` but `Wood_white.glb` -
and the probe that found them had tried one casing. All twenty exist and the
live viewer works. The argument for one model was never that his site was
broken; it is 180 MB against 9 MB, and instant switching against a download
per click.

## Why one file is enough

Every one of those twenty models is the **same single mesh** - one node, one
mesh, seven primitives, identical to within a few dozen bytes - and differs
only in what its materials are set to. Blender glTF exporter 4.1, no Draco, geometry
in the BIN chunk, and only the woodgrain files carry a texture (a 1024x1024
PNG, 1.17 MB, which is the whole of the 1.2 MB difference).

The materials are named by role, which is the part that makes this work:

| material | what it is | this viewer |
|---|---|---|
| `Silver` | hardware and track, metalness 0.98 | left alone |
| `Frame_white` / `Frane_Black` / `Frame_woodgrain` | the door's frame | **recoloured** |
| `Frame_bronze` | a piece that is dark (0.02 linear) in *every* one of his files, white and woodgrain included | left alone |
| `Glass_clear` / `_White` / `_green` / `_bronze` / `_grey` | the glazing, `KHR_materials_transmission` | **recoloured** |
| `Blue_Circle`, `White_Circle` | **the rollers** - the wheels down each side that run in the track | **black unless the frame is White** |

So: load one model, keep it, and set colours on its materials. One 8.8 MB
download instead of twenty, and every colour change instant.

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
3. **`Blue_Circle` and `White_Circle` are the rollers** (owner, 2026-10-27:
   "the rollers are the circular objects on the side of the door"), and every
   finish but White now gets them in black. White keeps whatever the file was
   built with. Confirmed against the mesh before changing anything: both
   materials sit on the back face, at both side edges, running up the height
   of the door, which is where rollers are and nothing else is.
4. **`Frane_Black`** is a typo in the Black files. Harmless; `FRAME_RE` matches
   `fra[mn]e` so it is picked up either way. Worth fixing at the source if
   those files are ever re-exported.
5. **The "small floating squares" are a PRIMITIVE, not a material** (owner,
   2026-10-27, with a screenshot: *"there are some small floating squares on the
   front side of the door ... change the color of those squares to always be
   black, unless the door is white in which case they should be white, just like
   the rollers"*).

   **The first attempt got this wrong** by reasoning from the material list
   alone: `Silver` was the only material never recoloured, so `Silver` looked
   like the answer, and painting it turned every hinge, bracket and the track
   black. His reply - *"what you changed the color of was all the parts which is
   not what i wanted"* - came with the picture, and the square in it is
   **woodgrain**. Frame material. A material-shaped answer was never going to
   reach it.

   His mesh carries the frame material **twice**:

   | primitive | what it is | extent across the door's thin axis |
   |---|---|---|
   | the big one, 8,083 verts | the real frame - stiles and rails | centred, 2.0 thick |
   | the other, 3,791 verts | **ten blocks and nothing else** - five up the left edge, five up the right, one at each section joint | reaches out to 3.8, where the face is at 1.0 |

   So they stand a whole door-thickness proud of the face, which is exactly why
   they read as squares hanging in the air.

   - **They are found by SHAPE, not by name.** The biggest frame mesh is the
     door; any other frame mesh reaching well beyond it along the door's own
     thin axis is one of these. No axis names, no vertex counts and no
     primitive indices are written down, so a different model measures itself -
     the same rule the lite bars are placed by. Measured: they reach **0.106**
     past the face where the threshold is **0.038**, so the margin is close to
     three times over.
   - **The material is CLONED first.** glTF shares one material between the
     door and the squares and three.js hands back the same object for both, so
     painting it where it stands would paint the whole door black.
   - **The map is cleared as well as the colour**, or a woodgrain door would
     keep woodgrain squares.
   - **White is written, not restored**, unlike the rollers - the point is to
     stop them taking the door's finish.

## GETTING OFF SIRV (owner, 2026-10-26)

*"we dont want to be using sirv, we want to unsubscribe from them to save
money so as long as this program you made works without them then we are
good."*

It does, and this is the whole of what that takes. **The viewer needs exactly
one of the twenty models** - the rest were only there because the old viewer
wanted a separate file per colour - so what has to move off Sirv is two files
totalling 9 MB.

**Do this while the Sirv account is still live:**

1. Download `https://davidaaigd.sirv.com/3d/White_Clear.glb` (8.8 MB). Worth
   taking a copy of the other nineteen as well, as a backup - they are not
   needed, but they cannot be fetched again afterwards.
2. In cPanel, File Manager, `public_html`, make a folder - say `door-preview`.
3. Upload `White_Clear.glb` and `woodgrain.jpg` into it.
4. Check it is served: open
   `https://aaimpactgaragedoor.com/door-preview/White_Clear.glb`. It should
   download. If it answers "Not Acceptable" or 403 that is HostGator's
   mod_security, and an `.htaccess` in that folder fixes it.
5. In `copy.html`, set the two paths to `/door-preview/White_Clear.glb` and
   `/door-preview/woodgrain.jpg`, copy the block, paste it on all three pages.
6. Cancel Sirv.

**Root-relative, starting with `/`.** A path like `door-preview/x.glb` would
resolve against `/products/series-1200/` and 404; a leading slash is right on
every page and on either protocol.

**The content type does not matter.** GLTFLoader fetches the model as an array
buffer, so a server calling it `application/octet-stream`, or anything else,
loads perfectly well. No MIME configuration is needed.

Same origin also means **no CORS**, which is one fewer thing that can fail
than the Sirv arrangement it replaces.

### three.js too, if nothing third-party is wanted

jsDelivr is free and not a subscription, so it is not what the Sirv bill was
about. But if the preference is that nothing at all comes from outside, upload
`static/lib/three.min.js` and `static/lib/GLTFLoader.js` into the same folder
and put their paths in the other two boxes on `copy.html`. The viewer takes
them from `data-three` and `data-gltf-loader` with no code change.

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
| `static/src/copy.html` | one button that puts the whole block on the clipboard, with the build id, the five steps, and boxes for where the model and texture live - **the page to send him** |

Every one of them fetches with caching off. A browser handing back a stale
`wordpress_embed.txt` made a working fix read as a failure once already; the
block states its build id in its own header and reports it as
`AADoorPreview.built`, and the test page says outright when it has been given
an old copy.

### Two improvements worth making later

- **Compress the mesh.** 8.8 MB of raw geometry for one door is heavy. Draco or
  meshopt should take it under 2 MB, which matters most on a phone.
- **Host the model next to the bundle.** It only needs Sirv because that is
  where it already is.
