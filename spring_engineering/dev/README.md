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
