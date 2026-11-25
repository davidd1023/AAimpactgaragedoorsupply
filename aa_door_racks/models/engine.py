"""Where a bundle of doors can go on the cantilever racks, and where it
SHOULD go. Pure Python - no ORM - so every rule can be tested on its own.

The owner's rules (2026-11-25), in inches:

* A rack side has arms along its length at fixed positions. A, B, C and D are
  two 74.5" units 60" apart: arms at 0, 74.5, 134.5 and 209. E is two 74"
  units on three posts: arms at 0, 74 and 148.
* A door may stick out 24" past the OUTER arms at either end, never more.
* A door of 10' (120") or less rests on 2 arms. Longer doors need 3 arms.
* A door that is longer than 10' but too short to reach 3 arms (an 11' door
  on A-D) rests on the WIDEST pair of arms - one 74.5" unit - when the side
  allows it (A-D do, E does not). Decided for the owner as the safest use.
* One door never rests on one arm, and two doors never share an arm
  (E's middle post has no room for two).
* The arms are 53" deep: two rows, BACK and FRONT. A back row is only
  reachable while the front row in front of it is empty.
* Bundles stack: same arms, same row, with a 1.5" board between doors and
  none under the bottom door. A level has a clear height (39" for level 1 on
  the floor legs, 36" above it, unlimited on the top level).
"""
from dataclasses import dataclass, field

EPS = 1e-6
UNLIMITED = 0.0


@dataclass
class Rules:
    panel_thickness: float = 3.25
    spacer: float = 1.5
    two_arm_max: float = 120.0      # 10' and under on two arms
    fallback_max: float = 132.0     # 11' doors on one unit where allowed


@dataclass
class SideSpec:
    key: object
    arms: list                      # positions in inches, ascending
    overhang: float = 24.0
    allow_fallback: bool = True
    levels: dict = field(default_factory=dict)   # level key -> clear height (0 = unlimited)
    level_numbers: dict = field(default_factory=dict)


@dataclass
class Placed:
    """One bundle already on a rack."""
    key: object
    side: object
    level: object
    depth: str                      # 'back' or 'front'
    arm_from: int
    arm_to: int
    start: float
    length: float
    height: float
    seq: int = 1
    blocked: bool = False           # a spot closed by an admin (something else stored there)

    @property
    def end(self):
        return self.start + self.length


@dataclass
class Candidate:
    side: object
    level: object
    depth: str
    arm_from: int
    arm_to: int
    start: float
    stacked: bool
    stack_height: float             # height of the stack once this bundle is on it
    score: float
    seq: int = 1


def bundle_height(door_panels, rules):
    """Panels x thickness, plus a board between doors (none under the bottom)."""
    doors = [p for p in door_panels if p]
    if not doors:
        return 0.0
    return sum(doors) * rules.panel_thickness + rules.spacer * (len(doors) - 1)


def support_groups(side, length, rules):
    """Arm groups (i, j) - consecutive arms i..j - a door of this length may
    rest on, by the owner's rules."""
    arms = side.arms
    n = len(arms)
    pairs = [(i, i + 1) for i in range(n - 1)
             if length + EPS >= arms[i + 1] - arms[i]]
    if length <= rules.two_arm_max + EPS:
        return pairs
    triples = [(i, i + 2) for i in range(n - 2)
               if length + EPS >= arms[i + 2] - arms[i]]
    if triples:
        return triples
    if side.allow_fallback and length <= rules.fallback_max + EPS and pairs:
        widest = max(arms[j] - arms[i] for i, j in pairs)
        return [(i, j) for i, j in pairs if arms[j] - arms[i] >= widest - EPS]
    return []


def start_range(side, i, j, length):
    """The range of left-end positions that put a door on arms i..j and on
    no other arm, inside the 24" overhang limit. None when impossible."""
    arms = side.arms
    lo = max(arms[0] - side.overhang, arms[j] - length)
    hi = min(arms[-1] + side.overhang - length, arms[i])
    if i > 0:
        lo = max(lo, arms[i - 1] + 0.01)
    if j < len(arms) - 1:
        hi = min(hi, arms[j + 1] - 0.01 - length)
    if lo > hi + EPS:
        return None
    return lo, hi


def _stacks(placed):
    """Group placed bundles into stacks: same level, row and arms."""
    stacks = {}
    for p in placed:
        stacks.setdefault((p.level, p.depth, p.arm_from, p.arm_to), []).append(p)
    for members in stacks.values():
        members.sort(key=lambda p: p.seq)
    return stacks


def _stack_height(members, rules):
    return sum(m.height for m in members) + rules.spacer * (len(members) - 1)


def _free_start(lo, hi, preferred, length, blocked):
    """A start in [lo, hi] closest to `preferred` that keeps the door clear of
    every (start, end) interval in `blocked`. None if there is none."""
    allowed = [(lo, hi)]
    for s, e in blocked:
        bad_lo, bad_hi = s - length, e         # starts inside (bad_lo, bad_hi) overlap
        nxt = []
        for a, b in allowed:
            if b <= bad_lo + EPS or a >= bad_hi - EPS:
                nxt.append((a, b))
                continue
            if a < bad_lo + EPS:
                nxt.append((a, bad_lo))
            if b > bad_hi - EPS:
                nxt.append((bad_hi, b))
        allowed = nxt
    best = None
    for a, b in allowed:
        if a > b + EPS:
            continue
        x = min(max(preferred, a), b)
        if best is None or abs(x - preferred) < abs(best - preferred):
            best = x
    return best


def _isolated_arms(n, used):
    """Free arms with no free neighbour - nothing can ever rest on them."""
    count = 0
    for k in range(n):
        if k in used:
            continue
        if (k - 1 not in used and k - 1 >= 0) or (k + 1 not in used and k + 1 < n):
            continue
        count += 1
    return count


def candidates(sides, placed, length, height, rules, exclude=None):
    """Every place a bundle (length, height) can go, best first."""
    placed = [p for p in placed if p.key != exclude]
    out = []
    for side in sides:
        groups = support_groups(side, length, rules)
        if not groups:
            continue
        n = len(side.arms)
        mine = [p for p in placed if p.side == side.key]
        stacks = _stacks(mine)
        for level, clearance in side.levels.items():
            level_no = side.level_numbers.get(level, 1)
            for depth in ("back", "front"):
                row = {k: v for k, v in stacks.items() if k[0] == level and k[1] == depth}
                front = {k: v for k, v in stacks.items() if k[0] == level and k[1] == "front"}
                used_arms = set()
                for (_l, _d, a, b) in row:
                    used_arms.update(range(a, b + 1))
                for i, j in groups:
                    rng = start_range(side, i, j, length)
                    if not rng:
                        continue
                    group_arms = set(range(i, j + 1))
                    if depth == "back":
                        # the forklift reaches the back only past an empty front
                        if any(group_arms & set(range(a, b + 1)) for (_l, _d, a, b) in front):
                            continue
                    preferred = (side.arms[i] + side.arms[j]) / 2.0 - length / 2.0
                    own = row.get((level, depth, i, j))
                    others = [(min(m.start for m in v), max(m.end for m in v))
                              for k, v in row.items() if k != (level, depth, i, j)]
                    if own and any(m.blocked for m in own):
                        continue
                    if own:
                        # on top of the stack already on these arms
                        if any(group_arms & set(range(a, b + 1))
                               for (_l, _d, a, b) in row if (a, b) != (i, j)):
                            continue
                        new_h = _stack_height(own, rules) + rules.spacer + height
                        stacked = True
                        seq = max(m.seq for m in own) + 1
                    else:
                        if group_arms & used_arms:
                            continue
                        new_h = height
                        stacked = False
                        seq = 1
                    if clearance and new_h > clearance + EPS:
                        continue
                    start = _free_start(rng[0], rng[1], preferred, length, others)
                    if start is None:
                        continue
                    isolated = _isolated_arms(n, used_arms | group_arms)
                    row_extent = side.arms[-1] - side.arms[0] + 2 * side.overhang
                    waste = (row_extent - length) if j - i >= 2 else 0.0
                    if clearance:
                        height_frac = (clearance - new_h) / clearance
                    else:
                        height_frac = 0.8 if new_h <= 39 else 0.2
                    score = (1000 * isolated
                             + (0 if (stacked or row) else 150)
                             + 100 * height_frac
                             + waste
                             + (8 if depth == "front" else 0)
                             + 2 * level_no
                             - (40 if stacked else 0))
                    out.append(Candidate(side.key, level, depth, i, j, round(start, 2),
                                         stacked, round(new_h, 2), round(score, 2), seq))
    out.sort(key=lambda c: (c.score, str(c.side), str(c.level), c.depth, c.arm_from))
    return out


def fits(sides, placed, length, height, rules, side, level, depth, arm_from, arm_to,
         exclude=None):
    """The candidate for exactly this spot, or None if it does not fit."""
    for c in candidates(sides, placed, length, height, rules, exclude=exclude):
        if (c.side, c.level, c.depth, c.arm_from, c.arm_to) == (side, level, depth, arm_from, arm_to):
            return c
    return None
