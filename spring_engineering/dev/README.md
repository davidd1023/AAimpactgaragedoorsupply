# Duplex regression suite

Developer tooling. **Not** shipped: nothing here is listed in `__manifest__.py`
and nothing lives under `static/`, so Odoo never bundles or serves it.

```bash
node dev/replay.mjs                   # everything
node dev/replay.mjs --only=single     # just the Single golden
node dev/replay.mjs --only=invariants # just the Duplex laws
node dev/worklist.mjs [drum]          # what to measure next
```

No dependencies, no build step. `harness.mjs` imports the **same**
`static/src/js/spring_engineering.js` the manifest ships, with OWL stubbed, so
there is no second copy to drift out of sync.

## Why this exists

The Duplex model is reverse-engineered from readings taken by hand off the
manufacturer's reference calculator. Those readings were never stored, so every
recalibration was blind, and the git log shows the result: a run of refits that
each fixed one case and broke another. The source comments say so themselves —
*"reproduces the sweep above exactly and breaks SEVEN other readings"*.

Nothing could be verified, so nothing stayed fixed. That is what this suite is
for.

## The three sections

### 1. Single golden — *must not move*

`golden-single.json` is a snapshot of 725 Single-assembly cases: both end-coil
regimes, all three standard drums, all three hi-lift drums, every track radius,
vertical lift, the pitch input, and spring counts 1–4.

The Single path is **known good and is not being worked on**. This section
exists purely to prove that Duplex work does not disturb it. A diff here means
stop and fix it, not re-record.

Re-record only when the grid itself is deliberately widened:

```bash
node dev/replay.mjs --update-golden
```

### 2. Duplex invariants — no reference data needed

Laws the model must obey regardless of any reading. These are not opinions
about the reference calculator; each one is something the source comments
already assert, now enforced:

| Invariant | Why it must hold |
|---|---|
| wire choice independent of **door height** | peak torque is `weight × rEff`; height does not enter it |
| wire choice independent of **track radius** | radius moves turns and the multiplier inversely, so their product is fixed |
| heavier door never gets a **softer** pair | stiffness is the ladder's own ordering |
| chosen pair **meets the target** when one on the ladder can | otherwise it is a selection bug, not a calibration limit |
| every offered pair is **buildable** | inner must fit inside outer; each wire inside its ID's band |

These catch the whole class of bug where a continuous wobble flips a *discrete*
wire choice and moves the answer by inches — which is what the 1-decimal
rounding was doing: 85 weights changed wire with height alone, and 105
weight/spring-count combinations changed wire with radius alone.

### 3. Reference corpus — accuracy

`corpus.json`. The only section that can confirm the numbers are *right* rather
than merely self-consistent.

- `status: "verified"` — full inputs and outputs. Asserted by `replay.mjs`.
- `status: "partial"` — recovered from a comment but missing inputs. Not
  asserted; this is the re-measurement worklist.

## Where the model stands

Against 39 reference-API readings on the D400-144, all assertable:

| | before this work | now |
|---|---|---|
| wire choice | 8/11 | **44/45** |
| corpus reproduced exactly | — | **44/45** |
| Single assembly | — | **725/725 byte-identical** |

Readings now span all three standard drums, 1-2 springs, door heights 6'4" to
10'4", weights 200-750 lb and cycle targets 10,000-200,000.

### Drum independence: verified

Every reading was on the D400-144 until a six-reading set on the D400-96 and
D525-216 was taken specifically to test it. **Wire choice came back 6/6.** The
D525-216's effective radius is 28% above the D400s', which is precisely what
the old `tau` threshold could not survive; with `tau` gone there is nothing
left that can be drum-specific. This closes the original complaint that the
calculator "sucks for any drum that isn't 400-144".

### What is derived, with no fitted constant

- **Active length** — `springs x (divider_outer + divider_inner) / TIPPT`, the
  catalog formula, the same shape the Single path uses. Exact under 34".
- **Pairing ladder** — `duplexPairBalanced`. The outer spring is never
  materially more stressed than the inner across all 17 observed pairings.
- **Spring-count scaling** — exactly linear for length, exactly reciprocal for
  torque. The old single fitted exponent served both jobs and did neither.
- **Height and radius independence** — selection runs on exact values, so the
  reference's own 1-decimal rounding no longer flips a discrete wire choice.

### What is measured, and how well

- **`K`, per rung** — derived by inverting the reference's own reported cycle
  counts, not fitted to brackets. All 17 rungs covered; the four best-sampled
  agree to 0.17-2.05% across 9-10 readings each.
- **Acceptance fraction** — `DUPLEX_ACCEPT_FRACTION`. Two rejection boundaries
  put the reference at 0.90 of target; 0.95 is used here because this model's
  `K` carries ~1% from the reference's cycle rounding.
- **Length thresholds** — `tLo`/`tHi` on three densely-swept rungs, 9/9 each.
  Rungs with one or two readings deliberately get none and fall back to
  `round(active)`.

### What is still open

| | state |
|---|---|
| quarter inch on unswept rungs | structure known, needs a 9-point sweep per rung |
| springs over 40" | unexplained; 4 readings, the reference accepts a 2.6% rate error |
| the 200 lb reading | the reference rejects its own answer (over the 350,000 cycle max) |
| pair 2 and the two aliases | no reference readings at all |

### Three compensating errors, now gone

Each was provably wrong and each measured WORSE when corrected alone, which is
why fifteen commits of recalibration kept trading one case for another:

| | was | fixing it alone |
|---|---|---|
| strict accept-the-target | really 0.90 | 15/27 → 11/27 |
| `DUPLEX_CATALOGUE` cap | contradicted at 50k | 9/11 → 8/11 |
| `kSlope` line for `K` | ~8.5% low | 18/24 → 9/24 |

`K` was the one underneath. With it measured, the other two could be removed
and the threshold loosened, and all three then reinforced instead of fighting.

## Taking readings that are actually worth taking

The highest-value readings now are the ones that pin down what is still open:

1. **The quarter-inch regime.** More readings on `0.2625/0.2253` at 2 springs,
   sweeping weight across 440-480 lb in 5 lb steps, to find exactly where the
   1.25" step falls and whether it recurs.
2. **The cycle model.** Any reading where the app picks one step too stiff.
3. **`round` against `floor`.** Still unsettled: every confirmed whole-inch
   reading has a fractional part below 0.5, so both reproduce all of them.

Record both sides of any step, and put the raw API response in `source`.

## Hi-lift (batches 5-7, 2026-10-02)

Hi-lift turned out to need **no new selection machinery**: it enters only
through the multiplier, and everything downstream - the wire ladder, `K`, the
length bands - is a function of TIPPT. That was worth proving rather than
assuming, and the proof is cheap: re-run a failing case with the reference's
own `multiplier` substituted for ours. On all seven initial length misses the
answer did not move, so the multiplier surface was not the cause.

| | result |
|---|---|
| 131 distinct hi-lift readings | wire and length |
| in sample | 127/131 |
| **5-fold holdout, out of sample** | **206/211 (97.6%)** |

Every out-of-sample miss is one of the four already-known in-sample failures,
so the bands are not overfitted to hi-lift.

What the sweeps actually bought:

- **`hiLift` is the request parameter.** Eight guesses failed; one real URL
  from the user settled it. One real request beats any amount of probing.
- **The config payload's drum list is standard-lift only.** `575-120` and
  `525-54HL` work fine with `lift=HiLift` despite being absent from it, and
  `D800-312` is refused with it. Absence from that list means nothing.
- **575-120 and 525-54HL clamp the door weight at 1000 lb**; 1005 already
  comes back as 1000. `D800-120` does not clamp - it tracks the entered weight
  exactly to 2000 lb. Found by backing the weight out of the reference's own
  `totalInchPoundPerTurn / multiplier`, which is the cheapest way to see what
  the reference thinks the inputs are.
- **One drum is not a family.** Batch 5 scored 47/47 on `D800-120` and it was
  tempting to call hi-lift done. The 575 family, swept next, came in at 60/64
  on wire. Validate per multiplier surface, not per feature.

### Still open on hi-lift

- 850 lb / 2 springs / 575-120 picks one step too soft, and 1000 lb /
  4 springs / `hl60` picks the inner one step too soft.
- 1800 and 2000 lb on `D800-120` want `0.5312/0.4218` and `0.5625/0.4305`,
  rungs the ladder does not reach. Two readings cannot pin a rung's `K`, so
  these need a sweep of their own before they can be fixed.
- The HL575 multiplier surface drifts to 9.9e-05 at a 192" door on
  `525-54HL`, well past the 2.1e-04 worst case but worth watching, since a
  large enough multiplier error eventually flips a length rounding.

## Two ingestion bugs that cost real accuracy

Both were silent, and both are the same shape: the fitter was fine, the input
was wrong. Worth re-reading before adding any new data source.

**1. Every reading was counted twice.** `derive.mjs` reads `pulled*.json` AND
`corpus.json`, and `import.mjs` folds pulls into the corpus - so from the
moment the import workflow started, almost every reading arrived twice.
Uniform double-counting cancels, which is why it hid for eight batches. It
stopped cancelling the moment one group was weighted differently: hi-lift
lived only in the pulls (1x) while standard lift was in both (2x), so hi-lift
lost every tie. Importing the hi-lift readings made them 2x too, they started
winning those ties, and **38 standard-lift readings broke**. The fix is the
dedup pass in `derive.mjs`; it also checks that identical inputs never carry
different outputs, and across 4099 ingested rows there were **zero** such
collisions, which is good evidence the reference is deterministic and the
labelling is right.

**2. The hi-lift holdout withheld nothing.** It keyed on a `hiLift` marker set
only in the pull path, so once the readings were also in the corpus it
withheld one copy and left the other in the fit - and reported a perfect
out-of-sample score that was really in-sample. It now runs after the dedup
pass, and the corpus path sets the marker too.

The general lesson: **a holdout that reports a suspiciously good number is
itself a thing to test.** Both bugs were found by distrusting a good result,
not a bad one.

## dev/import.mjs

`corpus.json` is what `replay.mjs` asserts against; `derive.mjs` reads the
pulls directly. So a pull could teach the model a band and never enter the
regression suite - nothing would notice if a later derive broke it. That is
exactly what happened to hi-lift: 47 readings trained the bands while only one
hi-lift reading was ever asserted. Importing was being done by hand, so now:

```sh
node dev/import.mjs dev/pulled-hl5.json hl5 "what this batch was for"
```

It applies the same strict filter the deriver does - Duplex only, the
calibrated pair only, both springs present, a recognised lift - and reports
what it skipped instead of dropping rows quietly.

## The holdout was flattered by where I looked

`dev/coverage.mjs` walks the ALLOWED parameter box per drum - weight to
`maxWeight`, height to `maxHeight`, every spring count, every radius the drum
offers, every cycle target - and counts cells with no reading in them:

| drum | cells | covered | % |
|---|---|---|---|
| D525-216 | 26,208 | 405 | 1.5% |
| D800-120 | 9,660 | 64 | 0.7% |
| D400-144 | 5,544 | 103 | 1.9% |
| 575-120 | 4,340 | 40 | 0.9% |
| 525-54HL | 4,340 | 25 | 0.6% |
| D400-96 | 1,092 | 7 | 0.6% |
| **total** | **51,184** | **644** | **1.3%** |

2,797 readings cover 1.3% of the box, and the biggest hole on every single
drum is the same one: **one spring at a 15,000 target**.

`dev/by-drum.mjs` overstates this, and it took a direct question to notice.
"weights 216-1500 (789)" says nothing about whether the 789 are spread across
spring counts, radii and targets or piled into one corner - and they were
piled. A drum with no failures and no coverage reads exactly like a verified
drum.

### Why the five-fold holdout did not catch it

The holdout withholds CORPUS readings, so it inherits the corpus's bias. It
answers "can the model predict a reading like the ones it was fitted on",
which is not the same question as "can it predict a door someone might quote".
It reported 98.0% while an unbiased sample of the same box came in far lower
on length.

The fix is `dev/sweeps-rand.json`: cases drawn uniformly at random from the
allowed box with a fixed seed, pulled fresh. Nobody chose those coordinates,
so the score on them is an honest estimate. **Draw a NEW seed after fitting to
them** - once they are in the corpus they are training data like anything else,
and scoring on them says nothing.

### What it found

Active length is the axis the corpus never covered:

| active length | corpus readings | length correct |
|---|---|---|
| under 20" | 593 | 100.0% |
| 20-30" | 789 | 99.6% |
| 30-40" | 528 | 100.0% |
| 40-60" | 558 | 100.0% |
| 60-90" | 48 | 100.0% |
| over 90" | ~1 | - |

2,468 of 2,517 readings sit below 60". The random sample reaches far past
that, because a light door on a 300,000-cycle target gives a very long spring,
and the length rule had never been tested there. Multiplier and wire choice
held up at 100% on the sample; only length moved.

## Where this ended up, and why it is not 100%

Run `sh dev/honest.sh`. It prints both numbers, because quoting the first alone
is misleading:

| | | |
|---|---|---|
| in sample | 3153/3181 | what the fitter reproduces of what it was shown |
| external, seed 777001 | wire 98.7%, length 68.0%, within 1" 92.9% | 225 readings |
| external, spread sample | wire 100.0%, length 66.3%, within 1" 93.2% | 294 readings |

Two independent uniform draws from the allowed box agree, so ~**99% on wire,
~67% exact on length, ~93% within an inch** is the real figure. The wire is the
part that decides which spring to order.

### The length rule cannot be finished in this model class

`(rung, spring count, fraction)` provably does not determine the reference's
length. The proof is in the deriver's own output on the biggest group in the
box - `0.2625/0.2253` at four springs, a quarter of everywhere a random door
lands:

```
RUNGS WHERE THE FRACTION ALONE DOES NOT DETERMINE THE LENGTH
  0.2625/0.2253 at 4 spring(s): 97 bands needed over 214 readings
RUNGS WHERE ONE THRESHOLD CANNOT FIT THE READINGS
  0.2625/0.2253 at 4 spring(s): bonus is not monotonic in frac
```

Three independent lines of evidence say the same thing:

1. **A predictor search.** `(rung, springs, frac)` caps at 92.6% and already
   needs 1355 groups for 3173 readings. Adding `floor` reaches 99.7% with 2535
   groups - 1.25 readings per group, which is a lookup table, not a rule. Turns,
   coils and coil-fraction all score ~45%, no better than guessing the modal
   value.
2. **Adding good data makes it worse.** A 300-reading sample with height,
   target and weight drawn independently - properly spread - dropped the
   external score from 68.0% to 64.9% AND the in-sample score from 3153 to
   3092, without being asserted at all. Valid readings that make the fitter
   worse at reproducing the existing corpus mean the new readings contradict
   the old ones inside a group. That sample is kept as
   `dev/eval-soft2-spread.json` and is now the second evaluation set.
3. **Model complexity does not help in either direction.** Fewer bands is
   worse (2 bands: 60.0%, 4: 62.7%, 8: 63.6%, 64: 68.0%), and more is
   identical (128 and 64 agree exactly, because no group exceeds 64). K
   parallel thresholds, built specifically for the four-level group, scored
   158/239 at two levels against 157/239 at three and four.

What would actually close it is the reference's own length algorithm, or enough
readings per group to learn a 20-bucket fraction map for each of 150 groups -
on the order of 15,000 requests, at one per second, and even then capped near
92.6%.

### Three measurement traps, all of which caught me

Every one produced a number that looked better than the truth.

1. **The deriver read its own evaluation set.** `pulled-rand.json` matched
   `pulled*.json`, and the pull writes incrementally, so every `apply.sh`
   folded more of the scoring set into the fit. Reported 91.9%; the honest
   figure was 63.6%. Evaluation pulls are now named `eval-*` and skipped.
2. **The five-fold holdout read 98%** against ~67% on a uniform draw, and could
   not have done otherwise: it withholds CORPUS readings, and the corpus is
   full of one-pound sweeps, so a withheld reading always has a neighbour one
   pound away. Locally dense, globally sparse. It answers "can the model
   predict a reading like the ones it was fitted on", which is not the question.
3. **A crashed report read as a clean bill.** The table printer assumed every
   spring count carried bands and threw on lines and splits. The overfit and
   contradiction reports print after the table, so they stopped running the
   moment lines were introduced - and "0 rungs where frac alone provably fails"
   was a crash, not a result. The diagnostic that explains the whole length
   problem had been suppressed for several commits.

The common thread: **distrust the number that improved.** Each of these was
found by noticing a figure that got better when nothing relevant had changed.

### Also learned about sweep design

A 430-reading sweep of the highest-traffic rung took it from 58.3% to 29.2%.
Weight was varied finely at FIXED height and FIXED target - and since active
length is `springs*(dividers)/TIPPT` with `TIPPT = multiplier*weight`, at fixed
height that is simply proportional to `1/weight`. All 430 readings lay on one
one-dimensional curve through the (floor, fraction) plane, while the thing
being fitted is a surface over it. Dense is not diverse. It is kept as
`dev/biased-soft-weightonly.json`, excluded from fitting.

## Single was not fine, and the quarter inch is why

Single was believed exact. It was exact on the readings anyone had looked at,
and nowhere else, because nothing had ever compared its LENGTH to the
reference:

* `dev/single-check.mjs` checked only the MULTIPLIER, on hand-picked readings,
  and scored 12/12.
* the 725-case golden snapshot proves nothing MOVED, never that it was right.

Against 176 readings drawn uniformly from the allowed box, with the
reference's own wire choice fed back so the comparison is like for like:

| | before | after |
|---|---|---|
| multiplier within 2e-5 | 176/176 | 176/176 |
| length | **4/176 (2.3%)** | **175/176 (99.4%)** |

The reference quotes length on a quarter-inch grid - 30, 33.25, 51.5, 60,
85.75 - and `springLength` returned two decimals of the raw computation: 33.20
where the reference says 33.25. Springs are made to a quarter inch. Weight
follows the quoted length now too, which is 123/123 wherever the length agrees,
and that is not a guess: inverting the reference's own 7,941 reported weights
gives back the length it REPORTS, not the raw one.

`dev/single-external.mjs` is the check that was missing, and `sh dev/honest.sh`
runs it.

### A measurement bug that looked exactly like a model bug

Mid-investigation the Single multiplier read 124/176, with every failure at
radius 10 - 0 of 54, against 67/67 and 59/59 at radius 12 and 15. That looks
precisely like a broken LHR curve in the app. It was the scorer: the reference
encodes our "LHR" as radius 10, the Duplex scorers map it and the Single one
passed `"10"` straight through, so the app got a radius it does not offer,
found no turn-drop curve, dropped no turns and failed every one. With the
mapping added it is 176/176.

Worth remembering next time a failure is suspiciously total: **0 of 54 is a
wiring fault, not a model that is slightly off.**

## Duplex length: hypotheses tested and rejected

The Duplex active length is about an inch out and the bands absorb it. These
were each tested against the two external samples and each lost to the bands'
66.9%:

| hypothesis | result |
|---|---|
| quarter-inch quantisation, as Single | 8.3% |
| round to a whole inch | 15.7% |
| add an end-coils term, `endCoils * wire`, tried 2 to 8 coils | best 9.1% |
| nested springs sharing deflection: `t = a/L + b/(L+1)` solved as a quadratic | 11.7% |
| a scale factor on the active length | correlations 0.16, -0.09, -0.40, 0.23, sign flipping |
| inner divider only, outer only, harmonic, series | residual 17" to 37" wide against 2.39" |

The last row is the useful one: the CURRENT formula is right in structure, by a
wide margin. What it is missing is not a constant, a grid, a coil count, or a
different combination of the two dividers.

Single's formula is now proven exact, and it is
`(springs * divider) / tippt + endCoils * wire`. The Duplex one is
`springs * (div_out + div_in) / TIPPT`, which assumes both springs are the same
length when the reference's outer is exactly one inch longer. Correcting that
properly makes things worse, so the error is somewhere else again.

## The reference exposes its own drum table

`common-components-DVPRctXY.js` - the 662KB bundle the earlier search missed,
because it only looked at four of the eleven script tags - names three
endpoints that are not the calculator:

```
GET /spring-engineering/drum-list?liftType=Standard|HiLift|Vertical
GET /spring-engineering/drum?drumName=...
GET /spring-engineering/drum-recommendation
POST /custom/torsion-preview
```

`drum` returns the drum record, and it settles by authority what had been
inferred from names and probes:

| drum | maximumHeight | maximumWeight | we had |
|---|---|---|---|
| D400-96 | 96 | 530 | both correct |
| D400-144 | 144 | 750 | both correct |
| D525-216 | **231** | 1500 | height **216** - wrong by 15" |
| D800-120 | **384** | **2200** | neither |
| 575-120 | **264** | 1000 | weight only |
| 525-54HL | **234** | 1000 | weight only |

The D525-216 carries 231 inches despite its name, confirmed against the
calculator: the multiplier still moves at 228 and 231 and freezes at 0.202291
from 234, where the over-height warning starts. Capping at 216 shortened the
spring on any door between 217 and 231 inches.

The D800-120 note here used to say it had no weight cap, because the reference
tracked the entered weight exactly to 2000 lb. It does - 2000 is under 2200.
**Measuring inside a limit cannot find it**, and the record can.

The record also carries `flatMomentArm`, `highMomentArm`, `circumference`,
`rateOfRise` and `maximumCapacityFlat`, which are the real geometry behind the
fitted turns and multiplier curves. Those curves are already exact - Single
176/176, Duplex 99%+ - so they are left alone, but anyone revisiting them
should start there rather than refitting.

`drum-list` gives 79 standard-lift and 70 hi-lift drums against the 3 and 3 we
offer, which is the authoritative answer to which drums exist.

## Length: what is now PROVED, and what is left

Proved, so nobody needs to retest it:

* **Length is a function of (rung, spring count, TIPPT) and nothing else.** Of
  46 pairs sharing a rung, a spring count and a TIPPT but differing in turns by
  at least 0.3, 45 return the same length. Turns do not enter.
* **The grid is per spring count**, exactly: 1 spring is always a whole inch
  (1843 of 1843), 3 and 4 springs are always whole + 0.25 (594 and 413 of
  each), 2 springs is mixed - .0 on 793 and .25 on 274, and never .5 or .75.
* **The structure of the active length is right by a wide margin.** Residual
  spread is 2.39" against 17" to 37" for inner-only, outer-only, harmonic and
  series combinations of the two dividers.
* Lengths are **not** a stock list: 272 distinct values, nearly every whole
  inch from 10 to 119.

Rejected by measurement against the external samples, versus the bands' 66.9%:

| hypothesis | result |
|---|---|
| quarter-inch quantisation as in Single | 8.3% |
| whole-inch rounding | 15.7% |
| an end-coils term, 2 to 8 coils | best 9.1% |
| nested springs sharing deflection, `t = a/L + b/(L+1)` | 11.7% |
| snap the OUTER spring and subtract one | 29.5% |
| both dividers at one inside diameter | 0.0% |
| one shift per group - 83.7% in sample | **53.8%** |
| nearest neighbour in active length | 21.1% |

The one-shift row is the instructive one: a single parameter per group reaches
83.7% in sample and 53.8% out of it, while the bands reach 99% in and 67% out.
Simplifying the model does not rescue generalisation here, and neither does
adding freedom - both were tried and measured.

## The moment arm data: validation, not improvement

The drum record carries the real geometry, and it confirms that the fitted
constants in this file are physical quantities rather than curve-fitting
artefacts:

| our constant | what it is | record | agreement |
|---|---|---|---|
| `rEff` D400-96 | 2.2753521 | highMomentArm 2.275 | to published precision |
| `rEff` D400-144 | 2.2933549 | 2.293 | " |
| `rEff` D525-216 | 2.9364545 | 2.936 | " |
| `HL800_NODE_A` | 17.015618 | flatMomentArm 4.125² = 17.015625 | **seven figures** |
| `HL575_A` | 8.8176917 | 2.969² = 8.814961 | ours more precise |
| `spiralA` 525-54HL | 7.3952515 | 2.719² = 7.392961 | ours more precise |
| `spiralB` all | ~0.09966 | rateOfRise 0.313/π = 0.0996310 | ✓ |

So `rEff` is the drum's moment arm, `spiralA` is `flatMomentArm²` and `spiralB`
is `rateOfRise/π`. Nothing changes, because the fitted values carry four more
digits than the record publishes - but they are no longer magic numbers, and a
future maintainer can check them against the source.

One deliberate disagreement is worth keeping in mind: `HL800_A` is 17.0209238
where the record says 17.015625. The record publishes the catalogue nominal and
the calculator behaves like r0 = 4.1256. `HL800_NODE_A` holds the catalogue
value, which is why there are two. **Measuring the calculator beat reading the
catalogue.**

### What it does not give

`turnsCurve` is not in the record and cannot be derived from it. The record's
`circumference` gives turns as roughly `height/circumference + 1` - the extra
turn being the spiral first wrap - and that is accurate to about a tenth of a
turn:

| drum | height | our turns | height/circ | difference |
|---|---|---|---|---|
| D525-216 | 84 | 6.053 | 4.918 | 1.135 |
| D525-216 | 120 | 8.088 | 7.026 | 1.062 |
| D525-216 | 168 | 10.855 | 9.836 | 1.019 |
| D525-216 | 216 | 13.642 | 12.646 | 0.996 |

A tenth of a turn is a 1% multiplier error where this file holds 2e-5. Enough
to offer an unmeasured drum with a warning attached; not enough to match the
reference. Supporting any of the other 76 standard drums still needs readings
per drum, but the record supplies `maximumHeight`, `maximumWeight`,
`maximumDiameter` and the moment arm for free, so only the turns curve has to
be measured.

And it does not touch the length. The length problem is not geometric - the
multiplier is already exact to 2e-5 and the length is wrong anyway.

## The breakthrough: stiffness was measured, not computed

`duplexActiveLength` is `springs * S / TIPPT`, where S was the sum of the two
dividers. Because the reference reports BOTH its length and its TIPPT, S can be
solved from every single reading:

```
S = length * TIPPT / springs
```

Doing that across a rung's readings shows the computed S is wrong by up to
**4.6%**, and differently per rung:

| rung | computed S | implied S | error |
|---|---|---|---|
| 0.2625/0.2253 | 1015 | 1062 | +4.6% |
| 0.3625/0.283 | 4217 | 4124 | −2.2% |
| 0.4375/0.3625 | 11800 | 12156 | +3.0% |

On a 20" spring 4.6% is nearly an inch - **exactly the error the bands had been
absorbing for the whole project.** One fitted number per rung (`sMult`) fixes
the cause rather than the symptom.

Per RUNG, not per (rung, spring count): stiffness belongs to the wire pair, and
the measurement agrees - per rung generalises better with a third of the
parameters.

### Two things had to go with it

**The TIPPT must be the DISPLAYED one**, rounded to a decimal, the same rule
the cycle count and the MIP warning already follow. Using the exact value cost
ten points externally, because the length sits on a grid and a tiny TIPPT
difference flips the snap.

**The hand-written `long` override had to be deleted.** It predated all the
fitting and was compensating for precisely this stiffness error: on
0.2625/0.2253 at 3 springs it added +2.25" to an active length of 29.358,
giving 31.25 where the reference says 29.25. With `sMult` in place it is pure
damage:

| | seed 777001 | soft2 |
|---|---|---|
| with the long override | 73.8% / 92.4% | 66.3% / 85.4% |
| without it | **84.0% / 97.8%** | **87.4% / 98.0%** |

Earlier in the project that override measured as clearly correct - removing it
cost 48 corpus readings and took its rung from 55.6% to 36.1%. It was right
*given the broken stiffness*. A compensating constant looks load-bearing until
the thing it compensates for is fixed.

### Result

| | before | after |
|---|---|---|
| length exact | 67.4% | **86.4%** |
| within one inch | 95.9% | **99.4%** |
| off by more than an inch | 21 of 516 | **3 of 516** |
| in sample | 3161/3189 | 3156/3189 |

The grid is also now stated rather than fitted: 1 spring whole, 3 and 4 whole
plus a quarter, 2 springs whichever of the two is nearer.

## Chasing the exact inch: everything tried

`dev/variants.mjs` fits each candidate on the training pulls and scores it on
the readings the reference answers WITHOUT a message - the ones that get
ordered. Those are the only numbers below that mean anything; the in-sample
column is there to show how misleading it is.

| variant | in sample | CLEAN external |
|---|---|---|
| **A  sMult per rung** (shipped) | 90.7% | **84.6%** |
| B  sMult per (rung, spring count) | 88.4% | 71.5% |
| C  sMult + an integer shift per rung | 92.0% | 83.4% |
| D  sMult + additive inches per rung | **94.0%** | 82.3% |
| E  per-spring-count offsets as well | 90.5% | 84.7% |
| F  one global sMult from the wire ratio | 80.9% | 59.8% |
| G  per rung, geometry formula as fallback | 90.9% | 84.6% |
| H  fitted on clean readings only | 69.4% | 83.2% |

D fits best and generalises third-worst. Every attempt to add freedom lost, and
so did every attempt to remove it.

F is the interesting failure. `sMult` correlates strongly with the wire
geometry - r = **-0.9256** against the outer/inner wire ratio, -0.9008 against
the stress balance, +0.9175 against the inner spring's share of the stiffness -
so the divider formula is wrong as a smooth function of the pair. But replacing
43 fitted numbers with that one line drops the clean score from 84.6% to 59.8%,
so the per-rung values carry real information the trend does not.

### The two-spring grid, and where it stops

At two springs the reference lands on .0 for 808 readings and .25 for 402.
Sorting ONE rung by active length shows two parallel rules about an inch apart,
interleaved:

| active | ref length | offset |
|---|---|---|
| 14.18-14.45 | 15.25 | +1.0 |
| 14.84-15.00 | 15 | +0.05 |
| 15.14-15.55 | 16.25 | +1.0 |
| 15.70-15.97 | 16 | +0.05 |

Which rule applies is predicted by the **rung** at 87.2% and by nothing else:
drum 69.7%, radius 66.9%, target 66.8%, lift 66.8%, turns 66.8%, height band
66.8%, floor parity 66.8% - every one of those is just the .0 base rate, so
they predict nothing at all. Weight band reaches 80.5% on 37 buckets, which is
memorising.

Two readings of it were tested and rejected: a per-rung crossover LENGTH scored
91.0% in sample against 86.4% for a fixed offset, and 87.9% external against
89.1% - overfitting again. And the one-inch gap is not an inner/outer mix-up:
the reference's outer spring is exactly one inch longer than its inner on all
402 readings of the high rule and all 808 of the low one.

So roughly one two-spring reading in seven still varies within its rung with no
explanation found.

## The quarter inch, measured properly and still not solved (2026-10-05)

Three pulls this round, 492 readings. One of them helped. The other two are
written up here because each cost about four minutes of someone else's server
and would otherwise be run again.

### What the dense ladders actually showed

A 5 lb weight ladder (batch q1) plus 232 one-pound brackets across every
within-rung length step it found (batch q2) resolves the rule exactly on the
one rung dense enough to see it. On 0.2625/0.2253 at two springs, with
x = C/TIPPT and C = 2104, the boundaries in x fall at 15.62, 15.13, 14.62,
14.11, 13.63 - spaced almost exactly half an inch - and the rule is three
bands in frac(x):

    f <= 0.12        ->  floor + 0.25
    0.12 < f <= 0.62 ->  floor
    f > 0.62         ->  floor + 1.25

Both outer bands are "nearest integer plus a quarter"; the middle one is a
plain floor. It explains every reading on that rung.

It does not generalise. Fitted per rung and tested on held-out readings for
that SAME rung, it scores 66.1% against the shipped band table's 87.0%. With
the thresholds forced global it explains 76% of the dense data. They are
properties of a slice, not of a rung, which is why the ugly per-rung band
tables beat the clean rule.

### Two traps, both mine

A WEIGHT LADDER MOSTLY CANNOT SEE THE QUARTER AT ALL. Of 49 (rung, spring
count) groups in the dense data, 42 contain only whole lengths - 544 whole
against 43 quarters overall. Fitting three parameters to a group that has one
frac value collapses to `floor` and reports 98.9%, which is what my first
pass did. Only 7 groups could discriminate anything. A pull meant to settle
the quarter has to walk the FRACTION of the active length, not the weight;
batch 3 did that in 2026-10-02 and it is why those readings are worth more
than these.

"NO SINGLE CONSTANT CAN WORK" WAS MIS-PREMISED. The test asked whether
|L - C/TIPPT| could stay under 0.375 for some C, 0.375 being half the widest
gap in the {n, n+0.25} lattice. It cannot - the best is 0.48 to 0.61 - and I
briefly wrote that the whole form was wrong. But that bound only applies to
NEAREST-NEIGHBOUR snapping. Under a band rule a reading can sit 0.62 from the
value it maps to, so the measurement rules out the snap I assumed, not the
form that is shipped.

### Dense is not diverse, the second time

Folding the 232 one-pound brackets into the fit took clean length from 91.6%
to 89.6%. They are one drum, one height, one cycle target, varying only
weight - a line through the input space - and they outvote the diverse
readings on the rungs they touch. This is the same failure as the 430-reading
sweep noted above, which cost 29 points. The file is held out of dev/, not
imported.

### What did work: the long-spring region

Breaking the remaining clean misses down by input found the weak one:

    cycle target   50,000  97.5%        200,000  82.1%
                   10,000  93.2%        300,000  80.0%
                  100,000  90.6%

and 19 of 36 clean misses were a full inch or more rather than a quarter.
High targets mean long springs, 40 to 76 inches, where a small error in a
rung's scale crosses an integer - and the scales were fitted almost entirely
on short springs.

So batch L1 sampled that region DIVERSELY: every axis independent from a
seeded generator, six drums, three radii, 1-4 springs, heights 84-180,
targets 100k/200k/300k. It scored 87.7% before import, against 91.6% on the
mixed samples, confirming the region.

ONLY THE 114 CLEAN READINGS WERE KEPT. Including the 146 flagged ones cost
2.7 points of flagged accuracy and gained nothing: they are doors the
reference is already complaining about, usually about length, so their
lengths are the least trustworthy in the file. Clean-only took clean length
from 91.6% to 91.9% and moved nothing else.

That gain is one or two readings out of 431 and is inside the noise. It is
kept for the principle - 114 diverse readings in a measured thin region - not
for the number.

## Walking the fraction (batch F2, 2026-10-05)

The note above said a pull meant to settle the quarter inch has to walk the
FRACTION, not the weight. This is that pull, and it is the first in several
rounds to improve both numbers at once.

340 readings, 339 clean. Weights chosen so frac(active length) is covered in
twentieths across the six (rung, spring count) groups carrying 20 of the 32
remaining clean misses - the soft end at two springs, which is also the most
common configuration there is. Every sample comes from a DIFFERENT drum,
radius, cycle target and height, so frac is covered without the batch becoming
a line through the input space.

    clean length 91.9% -> 92.1%        flagged 80.8% -> 81.7%

### Orderable doors only, and why the first attempt was useless

The generator first scanned weight upward and took the first match, which on a
big drum means a very light door: springs so over-engineered the reference came
back with 4.6 million cycles and a warning. Flagged readings have the least
trustworthy lengths in the file, so those are no use for settling a rule. It
now requires our own warning set to be EMPTY and picks among all the clean
candidates a configuration offers rather than the first, so weight is not
correlated with the bucket. 12,712 flagged candidates were rejected.

### What it made visible

On 0.2625/0.2253 at three springs the rule is one threshold: bonus 0.25 below
frac 0.747 and 1.25 above, and it explains all 60 readings. The deriver found
the same line unaided once the data was in. One, four and three springs on that
rung all now carry two-parameter lines.

Two springs on that rung still gets 42 bands, and the reason is worth writing
down: its levels really are three. The fraction walk saw {0.25: 43, 1.25: 16,
0: 1} and looked like a clean two-level group with one stray reading, but
across all 217 readings the levels are {0: 37, 0.25: 131, 1.25: 49} - the third
level has 17% support, and restricting to orderable doors does not remove it
(35 of 182). So the band table is not purely overfitting there; the group is
genuinely not two-level in frac alone.

### A level supported by one reading in sixty is not a level

That investigation did find a real fault. The level COUNT alone decided whether
a group got a line or a band table, so a single stray reading could tip a clean
two-level group into memorising dozens of bands. fitLineAnyLevels now ignores
levels with less than 3% support when counting, and fits the line to the rest.

It is safe by construction: the caller still cross-validates line against bands
over ALL the readings, outlier included, and keeps the bands unless the line
wins out of sample. Dropping a level only lets the line be considered.

    bands 170 -> 156, lines 88 -> 91, every score unchanged

Two groups moved from bands to lines - 0.3125/0.25 at three springs and
0.4531/0.3625 at one. Fourteen fewer memorised parameters for identical
accuracy, which is worth having even though today's samples cannot show it.

## FIXED: the table is reproducible again

Found and fixed 2026-10-06. Move every dev/pulled-*.json aside, re-run
apply.sh, and the table is now byte-identical to the one in git.

### What it was

dev/derive.mjs collected its per-rung groups - every K, every length, every
band and line fitted from them - at the TOP of the file, straight off the
ingestion. The dedup and both holdouts sat two hundred lines further down.

So the fits read the RAW ingestion: 9452 entries against 4350 distinct. A
reading held in both a pull and the corpus was weighted TWICE, and only
boundsFromSwitches, called after the dedup, ever saw the clean set. Pull files
are gitignored and do not survive a rebuild, so on a fresh build the duplicates
were simply absent, the weighting changed, and apply.sh produced a different
table from the committed one - 96.8% against the 97.9% in git.

The holdouts had the mirror image of the same fault: they withheld readings
from an array the fits had already finished reading. They withheld nothing that
mattered, and any generalisation number taken through them was fiction. That is
worth knowing for anyone who trusted dev/holdout.sh before today.

The fix is an ordering one - dedup and holdouts now run BEFORE the groups are
built - and it is verified the only way that counts: derive with the pulls on
disk, derive without them, compare the files.

### What it cost, and why that is the right trade

    unreproducible, duplicates double-weighted   clean length 97.9%
    reproducible, every reading weighted once    clean length 94.7%
    the same, with LINE_SLACK re-measured        clean length 96.8%

The last line is the one to quote. LINE_SLACK was 0.03, picked when the fits
read the raw 9452-entry ingestion; deduplicating halved what each group holds,
so the same fraction became a much smaller allowance and groups that had been
lines fell back to bands. At 0.08 - flat through 0.12, so not a knife edge -
there are 71 bands rather than 119, the external samples read 96.8% and the
five-fold holdout agrees on direction, 92.1% to 92.3%.

Both line fitters have to share that constant. fitLineOwnSlopes kept a second
copy of the default and stayed on 0.03 when this was re-measured, which held
the fitter handling the hardest groups to less than half the other's budget -
worth 0.5 points on its own.

Two more thresholds were set under the duplicated regime and wanted the same
treatment, for the same reason: both decide whether a group gets a MODEL or a
band table, and both are fractions of a group that has just halved.

    LEVEL_SUPPORT  0.03 -> 0.06   a level below this share is treated as noise
    SPLIT_MIN_SIDE   12 -> 8      readings needed either side of a regime break

Together, and with the shared slack:

    clean length 96.3% -> 97.7%      flagged 84.4% -> 85.3%
    bands 119 -> 38                  lines 99 -> 110

Three knobs have now been moved against the external samples, so the five-fold
holdout is the check that matters rather than a formality. It agrees on
direction each time, 92.1% -> 92.3% -> 92.4%, and it is much the smaller
movement because the corpus behind it is mostly targeted batches while the
samples are uniform draws from the allowed box.

The duplicates were up-weighting whatever was in both places, which is every
recent batch - the fraction walks, which are the best-designed readings in the
file. Emphasising them helped, by accident, and unrepeatably.

3.2 points is a real loss and it is the honest number. A figure that cannot be
reproduced from what is committed is not an accuracy, it is a coincidence, and
every measurement stacked on top of it inherits the problem. The numbers quoted
from here are reproducible.

## Refining the boundaries, not the shape (batch R1, 2026-10-06)

A fraction walk covers frac in twentieths, which finds the SHAPE of a group's
rule. What was left wrong after four of them was not shape but PLACEMENT. Of
the ten remaining clean misses, measured against the thresholds their own
groups use:

    8 of 10 sat within 0.025 of a threshold
    6 of 10 sat within 0.007

A reading that close is decided by where the boundary lies to three decimals,
and a bucket 0.05 wide cannot say. So dev/frac-refine.mjs reads the thresholds
out of the shipped table, works out where each falls for the integer part a
candidate lands on - they move with it - and keeps only candidates within 0.03
of one, bucketed at 0.0025. 1659 such candidates found, 19171 discarded as too
far.

These are the hardest readings in the file by construction: they scored 75.2%
before import, against 97.7% overall.

    clean length 97.7% -> 97.9%     within 1" 99.1% -> 99.3%
    clean misses 10 -> 9, and the largest failing group cleared outright
    (0.2625/0.2253 at two springs, 3 misses -> 0)

LINE_SLACK needed re-measuring a second time, to 0.12. Boundary readings are
the noisiest for a line to absorb, so at 0.08 they pushed groups off the line
fitter and doubled the band count, 38 to 91. At 0.12 the accuracy holds with 38
bands and the holdout prefers it, 91.9% to 92.1%. The knob is a fraction of
what a group holds, so it is not a constant of the problem - it wants
re-measuring whenever the data underneath it changes.

### And the corpus has to win the dedup

Importing R1 broke reproducibility again, for the reason the corpus-first sort
was written to prevent: pulls are read first, so a reading held in both places
is represented by its PULL copy, and once that pull is lost to a rebuild the
corpus copy takes over and the fit differs. The sort was tried earlier and
appeared to do nothing, because at that time the fits were reading the raw
ingestion from above the dedup entirely. With that fixed, the sort is what
keeps the result stable - and it is verified the same way: derive with the
pulls, derive without, compare the files.

## Best fit wins, not first fit (2026-10-06)

The last three misses in one group turned on a detail of how the split fitter
chose between forms. 0.273/0.2253 at two springs is two regimes of three levels
each, split near floor 20:

    floors 10-19   0 low and middle, 1.25 at 0.76-0.95, 1 above 0.91
    floors 20+     0.25 below ~0.08, 0 in the middle, 1.25 above ~0.76

On the upper side the low threshold CLIMBS with the integer part - 0.01 at
floor 20, 0.11 by 26 - while the high one sits flat near 0.76. Two changes were
needed:

  A SPLIT'S SIDES MAY USE INDEPENDENT SLOPES. fitSplit could only hand its
  sides the shared-slope fitter, so a regime whose thresholds move apart could
  not be placed at all.

  AND THE BEST-FITTING FORM HAS TO WIN. Adding that was not enough, because the
  sides were taking the FIRST form that came inside the slack - so a shared
  slope still won, producing `b: 0.014` shared between both thresholds, which
  drags the high one from 0.65 at floor 20 to 0.73 by 26 against readings that
  put it flat near 0.76 throughout. The forms are now listed simplest first and
  a later one must be STRICTLY better to displace an earlier one, so nothing
  gains freedom it has not paid for.

    clean length 97.9% -> 98.6%     within 1" 99.3% -> 99.5%
    clean misses 9 -> 6, and that group 3 -> 0
    five-fold holdout 92.1% -> 92.2%, on a population 380 readings harder

What is left is six misses, one apiece in six groups, three of which have four
or fewer external readings between them - at that point the samples cannot
distinguish a model fault from a single awkward door.

## THE HONEST NUMBER IS ABOUT 90%, NOT 98.6% (2026-10-06)

Read this before quoting any accuracy from this file.

Three knobs were tuned against dev/eval-clean.json, eval-soft2-spread.json and
eval-rand-seed777001.json - LINE_SLACK twice, LEVEL_SUPPORT, SPLIT_MIN_SIDE -
and dev/miss-profile.mjs was run against those same files to choose which
groups to collect readings for. That is a lot of selection pressure on about
800 readings, and it compromised them as a measuring stick.

So a fresh uniform sample was drawn afterwards with dev/eval-sample.mjs, 380
readings over the whole allowed box, and nothing has been tuned against it:

                        FRESH SAMPLE    the tuned-against samples
    clean, wire             99.4%              100%
    clean, length           90.3%             98.6%
    clean, within 1"        97.7%             99.5%
    flagged, length         66.8%             84.7%

### It is not the population

The obvious excuse is that the fresh sample is harder - it is 52% hi-lift
across all six drums, while the old sets are 100% standard lift on three. Split
out, that excuse fails:

    standard lift   89.4%
    hi-lift         91.4%

Standard lift alone reads 89.4% on fresh data against about 98% on the old
sets, for the same drums. The gap is overfitting, not population.

### The tuning bought nothing

    slack  support  minside   FRESH   tuned-against   bands
     0.03    0.03     12      90.3%       97.2%        130
     0.08    0.06      8      90.3%       98.6%         38
     0.12    0.06      8      90.3%       98.6%         38
     0.12    0.03     12      90.9%       98.1%         71

Identical on fresh data. The 1.4 points were fitting. The settings are kept
only because at equal honest accuracy they are 38 bands instead of 130.

### The holdout was right all along

dev/holdout.sh reported 92.1% to 92.4% through all of this while the samples
reported 96% to 98.6%. The note under LINE_SLACK in derive.mjs argued the
samples were "the better guide to real use" because they are uniform draws and
the corpus behind the holdout is targeted. That reasoning was wrong: once a
sample has been tuned against, it stops being a guide to anything. 90.3% fresh
and 92.2% holdout are consistent with each other; 98.6% was the outlier and
should have been treated as the suspect figure.

### Rules from here

  dev/eval-validation-seed61006.json is for MEASURING, never for tuning or for
  choosing what to collect. The moment a knob is moved against it, it is spent
  and another draw is needed.

  Quote the fresh figure and the holdout. If they disagree with a sample that
  has been tuned against, the sample is wrong.

  dev/eval-sample.mjs draws a new one in seconds, and the pull is six minutes.
  That is cheap next to reporting a number that is eight points optimistic.

## The boundary-refinement batch was making things worse (2026-10-06)

Found with the fresh sample, and it is my own tool doing the damage.

dev/frac-refine.mjs picks readings that land within 0.03 of a threshold the
model already uses, to place that threshold more precisely. Batch R1 is 380 of
them. On the samples that had been tuned against it looked like a gain. On a
uniform draw it is a loss:

                       R1 in the fit   R1 out
    clean wire             99.4%        100%
    clean length           90.3%        91.4%
    clean within 1"        97.7%        98.3%
    five-fold holdout      92.19%       92.51%

Concentrating that much data at the boundaries over-weights them: the
thresholds move to fit the boundary readings and are worse for ordinary doors.
It is the "dense is not diverse" lesson again, one level subtler - data chosen
BY where the model's boundaries already sit is the densest kind there is, and
the concentration is invisible in the input space, which is where I was
checking for it.

The readings are kept, marked `fit: false`, so dev/replay.mjs still asserts
them and nothing is thrown away - they are perfectly good reference data, just
not a fair sample to fit. derive.mjs skips them.

### What else was tried and did not pay

  CENTRING sMult IN ITS PLATEAU. fitStiffness scores a COUNT, so many
  multipliers tie, and `ok > best.ok` with an ascending scan took the LOWEST of
  them every time - no margin on one side. Taking the midpoint of the widest
  tied run is better reasoning and bought two readings in 5157 on the holdout,
  with nine more bands. Reverted.

  REFITTING sMult AGAINST THE REAL OBJECTIVE. fitStiffness optimises against
  snapGrid, a nearest-neighbour snap, while the shipped model decides length
  with frac bands - so the multiplier is tuned for an objective the model does
  not use. Scanning every rung for a better multiplier UNDER THE SHIPPED MODEL:
  zero rungs would move, 5021/5064 either way. The bands are fitted after the
  multiplier and absorb whatever it chose, so the pair is already at a local
  optimum. Theoretically wrong, costs nothing.

  POOLING THE THRESHOLDS. If the high threshold were really a shared constant
  near 0.75, pooling it would cut variance. The 111 fitted first thresholds have
  a standard deviation of 0.231 and run from -0.35 to 0.82. They genuinely
  differ per group.

### Where this leaves it

In sample 99%, holdout 92.5%, fresh uniform 91.4%. The model reproduces what it
is shown almost perfectly and loses eight points on new doors, and the residual
errors are a whole inch, as often short as long, spread evenly across spring
count, lift, cycle target and length with no concentration left to attack.

The next real gain is probably not another fitting idea. It is a corpus drawn
UNIFORMLY rather than targeted: 5157 readings is plenty, but they are mostly
switch points, fraction walks and boundary refinements, which is exactly the
data that makes per-group bands overfit. Fitting on uniform draws would close
the gap from the other side.

## More uniform data is not monotonically better (batches U5-U8, 2026-10-07)

Four more uniform batches, 1600 readings, drawn exactly like U1-U4. They do not
help the number that matters, and the effect is consistent across two
independent sample sets rather than being noise:

                       validation clean   older clean   validation flagged   older flagged
    U1-U4 fitted            93.7%            97.9%           74.9%              87.8%
    U1-U8 fitted            91.4%            97.2%           76.5%              89.7%
    U1-U8, flagged out      92.6%            97.9%           67.4%              84.7%

So the second four batches TRADE clean accuracy for flagged accuracy. About
half of a uniform draw is flagged, so doubling the draw doubles the flagged
readings, and although their lengths are already excluded their pairing and
cycle count move K - which changes rung selection for ordinary doors too.

Clean readings are the ones that get ordered, so U5-U8 are held out of the fit
with `fit: false` and kept in the corpus as data. Nothing is thrown away: if
flagged accuracy ever matters more, the flag comes off and the numbers above
say what that costs.

The useful general point is that "fit the distribution you are scored on" is
right about the SHAPE of a draw and silent about its size. U1-U4 was worth 2.3
points of clean accuracy; U5-U8 was worth -2.3.

### And a correctness bug the test exposed

`fit: false` was implemented as a `continue` at ingestion, which looked
equivalent to excluding the reading and was not. A reading that never enters
`readings` cannot take part in the dedup, so it cannot block the copy of itself
sitting in a pull file - and the pull copy carries no flag, so it gets fitted.
Putting dev/pulled-U5..U8.json back raised the distinct count by exactly the
1522 readings meant to be held out, and changed the table.

They are now ingested, win the dedup the way corpus readings always do, and are
dropped where the fit is built. The table is byte-identical with those pulls on
disk or absent, which is what the flag was for. The warning in the previous
commit - that the pulls had to stay out of dev/ - was right about the symptom
and wrong about the cause: it was not that the pull path ignores the flag, it
was that the corpus path was removing its own ability to win.

## Four measurement fixes, and two leads that measured out (2026-10-07)

No accuracy change this round. Validation clean length is still 93.7%, and
everything below is either a tool that was lying or a lead that was followed
until the data said to stop.

### A diagnostic that invented its own inputs read 60% where the truth was 94%

A new tool to compare our multiplier, turns and TIPPT against the reference's
reported values put clean length at 60.3%, with standard lift at 34% and
hi-lift at 91%. That shape is exactly what a real bug localised to the standard
path would look like, and chasing it would have been hours.

The tool was wrong. It carried its own copy of the reading-to-state mapping,
written from memory, and mapped a track radius of 12 to `'12"'` where the
component wants `"12"`. An unrecognised radius falls back to a default instead
of failing, and the radius only matters on standard lift - so a typo in the
harness produced a perfectly plausible, perfectly localised fake defect.

It was caught by comparing against `dev/clean-cases.mjs`, which already
reported 93.7% on the same file. **A new tool that measures a number an
existing tool already reports gets checked against it before anything it says
is believed.** Four copies of that mapping existed, and they disagreed about
the door width too, so the mapping now lives once in `dev/ref-state.mjs` and
the three scorers import it. Their output is byte-identical after the move,
which is the point: the refactor was verified to change no measurement.

### The multiplier surface is genuinely poor on one drum, and it costs nothing

`dev/mult-survey.mjs` scores the drum multiplier against every reading that
reports one - including flagged ones, since a flag is about the spring chosen
and not the drum arithmetic, which roughly doubles the data:

| drum | n | exact | over 1e-5 | worst |
|---|---|---|---|---|
| D800-120 hi-lift | 375 | **4.8%** | 178 | **-1.66e-03** |
| 525-54HL hi-lift | 264 | 31.1% | 80 | 2.65e-04 |
| 575-120 hi-lift | 350 | 69.1% | 8 | -2.50e-05 |
| D525-216 standard | 325 | 68.9% | 6 | 1.00e-05 |
| D400-144 standard | 182 | 59.3% | 0 | 1.00e-06 |
| D400-96 standard | 49 | 79.6% | 0 | -1.00e-06 |

A 1.7e-03 error is about twenty times what it takes to flip a TIPPT rounding
and with it a whole inch of spring, so the D800-120 looks like the obvious
next fix. **It is not.** On the validation sample all ten clean length misses
with the right rung have an exactly correct multiplier, turns and TIPPT; the
six that differ upstream do so only in turns, which the length does not use.
Repairing the surface would move nothing measurable. It is a real inaccuracy
with no present consequence - recorded, not fitted.

Two of that table's original rows were artefacts of the tool rather than the
model: a 20" track radius and a drum we do not offer contributed an apparent
8.6e-02 error, and reading a 54" drum at 90" of hi-lift contributed 6.7e-03.
The survey now excludes what the module does not offer and anything past a
drum's own rating, because scoring a deliberate refusal measures the refusal.

### The reference tolerates a cycle shortfall - and that still does not fix it

We raise `duplex-cycles-low` on 390 readings the reference passes and agree on
173: crying wolf two to one. The note beside that warning says no threshold
separates the reference's warned readings from its quiet ones, which is true
of **our** computed count. Measured against the count the reference itself
reports, the rule is almost exact (`dev/cycle-rule.mjs`):

| rule | false alarms | missed |
|---|---|---|
| reported < target | 327 | 0 |
| reported <= 0.95 x target | 2 | 0 |
| **reported <= 0.90 x target** | **0** | **0** |
| reported <= 0.85 x target | 0 | 177 |

So it is not "below target" - it accepts roughly a 10% shortfall. But the rule
is far less pinned than that table suggests, and the tool now says so: all 177
warned readings are the **same target at the same ratio**, 10,000 at 0.9000.
The lowest ratio it stays quiet at is 0.9333. The tolerance is therefore
bracketed to (0.9000, 0.9333] and no tighter, and one warned reading at any
other target would settle it.

Knowing the rule does not let us apply it, which is the real finding. The rule
takes the reference's own cycle count, and ours is 2.6% out at a 10,000 target
against 0.17% at 300,000 - an error that shrinks with the target, which is the
signature of the reference's 1000-cycle quantisation and not of our model. The
warning stays a caution.

### Floor or round: 86% of residuals land in [0, 1000) and that proves nothing

`ours - reported` falls in [0, 1000) for 86% of readings, which is what
flooring to 1000 looks like. It is equally what rounding to 1000 looks like if
our own count runs about 500 high, and the two cannot be told apart from
pulled data: a multiplicative bias in our cycle law shifts every step point
together. A weight sweep over one fixed spring was tried for this and could
not resolve it either - the step points are only located to within a pound,
about 160 cycles here, which is the same size as the thing being measured.
Settling it needs a configuration whose exact cycle life is known independently
of our cycle law. Our displayed figure still rounds, unchanged, because
changing it on this evidence would be a guess.

### Two things the suite was reporting wrongly

**`dev/honest.sh` led with the wrong number.** It printed in-sample first and
left the never-tuned validation sample out entirely - which is how 98.6% came
to be quoted for a model that was really at 90%. It now runs validation first,
labels the older samples as tuned-against, and reads the invariant total from
the suite instead of the hardcoded `/16` that stopped matching when a
seventeenth invariant was added.

**The corpus asserted a drum we deliberately do not model.** One D800-312
reading could never pass, so the accuracy section was permanently red for a
reason that was not a regression - the same trap the 120" limit already had a
rule for. It is now named and not asserted.

**`dev/eval-sample.mjs` could destroy the yardstick.** It is a generator, and
run with one argument it silently overwrote its target with a fresh seedless
draw of inputs. It did exactly that to the 380-reading validation sample -
an hour of polling at one request a second - and only a committed copy got it
back. It now requires a seed and refuses to overwrite an existing file.

## The cycles-low warning was crying wolf, and the rule is a constant (2026-10-07)

`duplex-cycles-low` fired on 335 readings the reference passes against 173 it
agrees with - two false alarms for every real one, on the one warning a
customer is most likely to act on. It now fires on **4**, with the same 173
agreements and the same 5 misses. Validation accuracy is untouched at 93.7%:
this is the warning, not the model.

### The rule is an absolute floor at 10,000, not a fraction of the target

The note that used to sit beside this warning said the reference fires "when
its own reported count falls below about 0.95 of the target", that our count
was too coarse to apply that, and that scanning every threshold from 0.70 to
1.05 offered only a choice between missing all 184 and 393 false alarms.

Every one of those statements was true, and the conclusion was still wrong.
**0.70 to 1.05 of the target is a family of rules that does not contain the
answer**, and a search over the wrong family reports "no threshold works" no
matter how much data it is given. The answer is not in that family at all: the
reference warns when the life it computes falls below 10,000, whatever was
asked for. Over 6,355 distinct readings that rule has no exceptions in either
direction.

The giveaway was in the reference's own message the whole time - "cycle life
calculation of 9,000.00 is less than the **10,000 cycle minimum**" names a
constant, and it says 10,000 on a 300,000-cycle door too. Three things stop
fitting once it is read that way:

- **Every warned reading reports exactly 9,000 cycles**, at door weights from
  300 lb to 1,949 lb and across eleven rungs. A tolerance on the target cannot
  produce a single value over that spread; a floor at 10,000 can only produce
  the one bucket beneath it.
- **All of them have a target of 10,000**, which is why a fraction of the
  target fitted equally well and why the two readings looked identical.
- **Missing a high target is silent.** The same 459 lb door that is warned at a
  target of 10,000 is passed without comment at 25,000, 100,000 and 300,000.

### The pull that failed to discriminate, and why that was still the answer

A 48-reading sweep was taken to separate the two readings of the rule: a door
that cannot reach a 300,000 target but still beats 10,000 would be warned by a
tolerance and passed by a floor. **No such reading exists.** The reference's
own selection lands within 4% of the target on every one of them - lowest ratio
0.960 - and a further 24 Single readings never land below the target at all.

So the two rules cannot disagree on anything the reference will actually
produce, and the floor is the one that explains the single warned family
without a free parameter. The sweep was not wasted: "the window is empty by
construction" is why the corpus could never have settled this, and it is what
makes the floor safe to ship.

### The same trap twice in one session, in the measuring tools

The Single path got the same change and then had it reverted, because the five
false alarms that justified it were produced by the tool and not by the module.
`dev/eval-single.json` carries no spring count on some readings; the reference
defaults that to 2, and the tool defaulted it to 1 - putting a whole door on
one spring and computing 553 cycles where the reference reports 14,000. With
the default corrected the Single warning fires on none of 523 readings, and the
reference raises no cycle message on any of them either, so there is nothing
there to fix and nothing to measure a rule against. It keeps the rule it has.

That is the second time in this session that a defaulting difference in a
scoring tool produced a confident, plausible, perfectly localised fake defect -
the first was a track radius of 12 written as `'12"'`. Both were caught only by
checking a new number against one an existing tool already reported. The
mapping now lives once, in `dev/ref-state.mjs`, and **the rule is that a tool
measuring something another tool already measures gets reconciled with it
before anything it says is believed.**

## A missing import shipped, and why nothing here could see it (2026-10-07)

`onWillStart` was called in `setup()` and never added to the `@odoo/owl` import
line. The page threw `ReferenceError: onWillStart is not defined` on the first
mount, in production, on the branch it had been merged into. Every test in this
repository passed, before and after.

**Two independent reasons it was invisible, and both were in the harness.**

`dev/harness.mjs` built its component with `make`, which assigns state directly
and never calls `setup()`. The one function the browser runs on every single
mount was the one function nothing here ran. Eight thousand readings go through
`make`, and none of them touch a lifecycle hook.

Worse, the harness declared its own stub block - four `const`s for the names
the component happened to use. **A stub list written independently of the
import list cannot test the import list.** Had the suite called `setup()`, the
hardcoded block would have supplied the very name the module was missing and
the test would have passed anyway. The harness was not just failing to check
this; it was constructed so that it could not.

Both are fixed:

- the stubs are now **derived from the source's own import statements**, from a
  table keyed by module, and a name imported with no stub is a hard error
  rather than a silent undefined. Remove the import again and the harness
  reproduces the production error exactly: `onWillStart is not defined`.
- `mount()` runs `setup()` for real and awaits the lifecycle callbacks, with an
  injectable `rpc` whose default **throws**, so a test that forgets to install
  one fails instead of quietly scoring a component that received no rates.
- two invariants, because they fail in different circumstances. One mounts the
  component and checks that the rates fetch reaches the price and that a failed
  fetch withholds it. The other is static: every `useThing()` and `onThing()`
  the source calls must be imported or defined in it, which also covers hooks
  in branches no test reaches.

### What this says about how it was verified

The pricing work was checked by curling `/spring-calculator/rates` and
`/spring-calculator/add-to-cart`, by `dev/price-parity.sh`, and by the
invariants. All of those exercise the server and the arithmetic. **None of them
loads the page.** The rates fetch lives in `setup()`, so the one change whose
whole purpose was to run on mount was verified by every route except mounting.

The end-to-end check that would have caught it takes one command, and is now
the habit: fetch the page, find the frontend bundle, and read our module as
served. It shows the import directly -
`const{Component,onWillStart,useEffect,useState}=require("@odoo/owl")`.
