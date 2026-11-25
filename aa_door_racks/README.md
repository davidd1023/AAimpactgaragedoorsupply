# Door Racks

Where every finished AA Impact door sits on the cantilever racks at 9753
(Medley). Inventory > Door Racks > Rack Map.

## The racks (owner, 2026-11-25)

- Sides A, B (rack 1), C, D (rack 2) and E (rack 3, one-sided).
- Levels 1 to 5 from the floor up. Level 1 is the floor legs, 39" clear;
  levels 2-4 are 36"; level 5 has no limit.
- A-D: two 74.5" units 60" apart, arms at 0, 74.5, 134.5 and 209.
- E: two 74" units on three posts, arms at 0, 74 and 148.
- A door may stick out 24" past the outer arms at each end.
- Arms are 53" long, so each level has a BACK and a FRONT row. The back of a
  spot is only offered while the front of it is empty.

## The rules for a door

- 10' or less: two arms. Two such bundles fit side by side on A-D, one per unit.
- Longer: three arms.
- An 11' door cannot reach three arms on A-D, so it rests on one 74.5" unit
  (decided for the owner as the safest use of the space). E does not take it.
- Never one arm, and two doors never share an arm: E's middle post has no room.
- 5" is always left free above a stack so the forklift can lift it (Andy,
  2026-11-25: "obligatorio ... por lo menos de 3 a 5 pulgadas"), a setting.
- Stack height = panels x 3 1/4" (packed, with cardboard - measured by Andy 2026-11-25) + a 1.5" board between doors (none under the
  bottom door). A bundle may go on top of another on the same arms if the
  stack still fits the level.

All four numbers are in Inventory > Configuration > Settings > Door Racks;
the racks themselves are in Door Racks > Rack Setup.

## How it is used

- Receive Bundle: one line per door (AA order #, width, panels). Find a spot
  draws the best spot and the other options on the map; Save here stores it.
- The search box lights up the bundle holding an order.
- Click a bundle: its doors, Delivered per door, Label (4x6), and for an
  Inventory administrator Move and Take out (a door into its own bundle).
- A door whose AA order # is the PO Number of a Supply order leaves the rack
  by itself when that order's delivery is validated (Dispatched).

## Where to put a bundle

`models/engine.py` is plain Python and holds every rule. The score prefers,
in order: not stranding an arm nothing can use, stacking on or filling a row
already in use, the stack that best fills the level's height, the side whose
length fits the door best (a 16' door goes to E before taking a whole A-D
row), the back row, and lower levels.

New module: after merging, Apps > Update Apps List > Door Racks > Install.
