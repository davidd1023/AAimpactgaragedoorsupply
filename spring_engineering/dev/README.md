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

## Where the model stands (2026-10-07)

**This section is the current state. Everything below it is a dated log of how it
got here, and the older entries describe a model that no longer exists** - the
section that used to sit here still quoted 39 readings on one drum, 44/45, and
`tLo`/`tHi` thresholds that were replaced months of work ago. Figures in a log
entry are true as of that entry; figures here are maintained.

### The number to quote

Two uniform draws from the allowed box, neither of which any choice in this
repository has been made against:

| | seed 61006 | seed 20261007 |
|---|---|---|
| clean length | 95.4% | 93.7% |
| clean within 1" | 98.9% | 98.3% |
| clean wire | 99.4% | 98.9% |
| flagged length | 75.9% | 81.6% |

**Quote about 94.5% for a door the reference answers cleanly**, and treat
anything finer than about three points on a single draw as unmeasured: 175 clean
readings carry roughly +-1.7 points of sampling error, which is why there are two
draws and why changes are tested PAIRED on the same readings.

Clean and flagged are kept apart because a clean reading is one the reference
quotes without complaint, and those are the ones that get ordered.

### The supporting measures

- **Five-fold holdout**, about 90.5% on ~7,700 readings at a fixed corpus. Better
  powered than the draws and on a different population - the corpus is mostly
  targeted batches - so it decides direction and the draws confirm size. Only
  comparable between models fitted on the SAME corpus; use `SCORE_EXCLUDE` when a
  change moves readings in or out.
- **In sample**, which says only that the fitter reproduces what it was shown.
- **725 Single cases byte-identical** to their snapshot, and the Single
  multiplier exact on 288 of 288 external readings.
- **19 invariants**, which hold without reference data at all.

### What the model is

- **50 rungs**, each an outer and inner wire pairing, with a per-rung stiffness
  `sMult` and torsion constant `K`.
- **Per (rung, spring count) length rules** - a threshold line in the integer
  part, a regime split where a group is really two rules, or a band table where
  neither fits. Groups with nothing fitted fall back to the measured grid.
- `DUPLEX_ACCEPT_FRACTION` is **1.0**: the selected pairing must MEET the target.
  The 0.95 that used to be documented here was the cycles-low WARNING threshold,
  which is a different number and is now known to be an absolute 10,000 floor
  rather than a fraction of anything.

### What limits it

13 of 16 clean misses across both draws are **threshold placement** - the rule can
produce the bonus the reference used and puts its boundary on the wrong side of
that one reading. Upstream error is not the cause: all 16 misses have an exactly
correct TIPPT, and the 8 readings whose TIPPT is wrong all still land on the right
inch.

Placement does not transfer between groups, which is why the margin objective
helped and more boundary data does not - margin extracts more from the readings a
group already has, new readings only help where they land.

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

## Margin, not flatness: 93.7% to 94.9% on the never-tuned sample (2026-10-07)

| | before | after |
|---|---|---|
| validation clean length | 93.7% | **94.9%** |
| validation clean within 1" | 97.7% | **98.9%** |
| validation flagged length | 74.9% | 75.9% |
| tuned-sample clean length | 97.9% | 98.1% |
| five-fold holdout | 89.63% | 90.16% |

Same model size. In sample, held out, and on both external samples, clean and
flagged, all moved the same way - which is what a generalisation gain looks
like, as opposed to the trades that fifteen earlier recalibrations made.

### Where the misses actually were

Eight of ten landed within 0.025 of their own group's threshold and six within
0.007, with an exactly correct multiplier, turns and TIPPT upstream. So the rule
was right and the boundary was a hair from the reading that crossed it.

For a FIXED slope the fitter already placed the line as well as it can - midway
between the two readings that straddle it, which is the most room the data
allows. But the slope was chosen by **preferring the flattest among equal error
counts**, which takes no account of how much room that slope leaves. A slightly
steeper line can hold the same readings apart with twice the gap, and it was
being passed over. Margin is now the first tie-break and flatness the second, in
both threshold fitters - and for the multi-cut fitter the margin of a rule is
its TIGHTEST cut, because that is the one a new reading flips first.

### Two things that looked right and measured out

**Max-margin tie-breaking on the cut position**, for a fixed slope. The error
count steps by one at every reading, so ties between non-adjacent cuts are
possible and the scan took the leftmost. The derived table came out
**byte-identical**: with a unique optimum the centred cut already IS the
max-margin point. Reverted rather than shipped as a no-op with a long comment
explaining a benefit it did not have.

**Regularising by group support.** The in-sample/holdout gap looks exactly like
small groups overfitting, so accuracy was measured against the support behind
each rung. It does not track it at all - a miss at n=944, and 100% at n=20-50.
Shrinking low-support groups toward a pooled threshold would be fitting a
pattern that is not there.

### What the apparatus is worth, finally measured

The 48 bands and 126 lines sit on top of a one-line default - round the active
length onto the grid for that spring count - and the two had never been scored
against each other out of sample:

| | exact | within 1" |
|---|---|---|
| the fitted apparatus | **94.3%** | 98.3% |
| plain grid rounding | 81.0% | **99.4%** |

It earns its keep by 25 readings to 2. Note the one place rounding wins: when
the apparatus is wrong it is occasionally wrong by MORE than an inch, where
rounding never is.

### What is left, and what will not fix it

`dev/miss-kind.mjs` splits every miss into the only two kinds there are. Over
the four external samples: **13 placement, 3 missing level.** The length rule is
limited by where its boundaries sit, not by what they choose between - which is
why maximising margin bought 1.2 points and why adding levels can buy at most
0.5.

All three missing-level cases want a bonus the same rung already uses at another
spring count, so the level is real and only its use at that count is unobserved.
That is the one place where borrowing structure across spring counts has any
evidence behind it, and it is worth at most three readings in 605.

Accuracy by spring count says the same thing from another angle: 4 springs is
100% of 90 readings, 3 springs 98.5%, 1 spring 96.9%, and **2 springs 96.1%** -
the only count whose grid is mixed, so the only one that has to choose the
quarter as well as the inch, and it loses about equally on each (quarter 97.5%,
inch 97.2%). Within two springs the two-level rules are the weak spot at 94.4%
against 97.6% for three-level ones.

### One suggestion that was not acted on

Of the 16 clean misses, 12 are short and 4 long. That looks like a bias worth
correcting and it is not established: two-sided p is 0.077 for a fair coin. The
last time a bias was claimed here it came off a truncated histogram and had to
be withdrawn, so this one is recorded with its p-value and left alone.

## Two ways the money and the paperwork could go wrong (2026-10-07)

Neither of these is about the spring model. Both are about the cart, both were
found by testing a setting rather than by reading the code, and both were live.

### A price-included tax would have taken the whole markup

`total` is a price to be RECEIVED - supplier cost, times the markup, plus
labour - and `price_unit` is only the same figure when taxes are tax-excluded.
A company whose sales tax is configured as price-INCLUDED, which is normal in
much of the world and one checkbox away anywhere, makes `price_unit` the gross.
Measured by setting that one checkbox on this build: **a $1,460 quote booked
$1,269.57.** The cart showed $1,460, the customer paid $1,460, and $190 of margin
per assembly went to the tax authority. Nothing anywhere would have looked wrong.

The controller now reads back what Odoo itself computed as the net and closes the
gap, which needs no knowledge of tax types at all. **The correction is a ratio,
not a difference**, and that is the part worth remembering: adding the shortfall
is the obvious move and converges far too slowly, because under an included tax
the correction is itself taxed - each pass closes about 13% of a 15% gap, so
roughly sixty passes to reach half a cent. The first version used four and left a
cent on the table, which is how this was noticed. Scaling by `target/net` lands
exactly in one pass for any percentage tax.

`dev/price-parity.sh` now checks the whole chain instead of two thirds of it: the
page quotes it, the server computes it, and the order line NETS it. The net is
the only one of the three that is money. Verified it catches the fault before
trusting it - with the correction removed and the tax set to included it reports
NET DIFFERS on every Duplex case.

### The order line could be written by the customer

The description was built by interpolating the caller's own strings, and
`/spring-calculator/add-to-cart` is public and unauthenticated. One real request
produced this order line:

    Duplex (WARRANTY VOID), 2 springs
    Inner
    NOTE: substitute cheaper wire: 0.2625" wire, 3.75" ID, 19.0" long
    Door: 600 lb -- PAID IN FULL, ship immediately lb, 7ft
    Discount: 100% approved by manager, 10,000 cycles

The price was never reachable that way - the server recomputes it from the
geometry and ignores the browser, which is what price-parity checks. The
paperwork was: the line is what the person picking and shipping the order reads,
and a forged one that says "paid in full" costs a shipment.

**Filtering the strings would have been the wrong fix**, because it is a guess
about which characters are dangerous. The route now parses every descriptive
field into a number or a word from a list - assembly, spring role, door weight,
door height, cycle target - and renders the line from those, so no caller text
reaches it at all. A spec that does not parse is refused in the same way a bad
wire size already was.

`dev/spec-abuse.sh` posts ten hostile specs that must each be refused and one
legitimate spec that must still go through - a route that rejected everything
would pass half of that test and be useless. It fails against the previous
controller, which is how it earned its place.

## The supplier costs were in the public bundle (2026-10-07)

`STEEL_PRICE_PER_LB` and `CONE_PRICES` lived in
`static/src/js/spring_engineering.js`, where the controller parsed them out of
the source. The reasoning was that one file should be the single place the costs
are written down - right about the principle, wrong about the file, because
everything under `static/` is served to anybody who opens the page. A visitor
could read this out of the frontend bundle:

    STEEL_PRICE_PER_LB=1.46
    CONE_PRICES={2.625:4.99,3.75:11.55,5.25:19.43,6:19.43,}

**That is worse than it first looks.** The markup percentage is kept off the wire
deliberately - `/spring-calculator/rates` sends the rates with it already applied
and never the figure itself - but publishing the costs makes the markup one
division away from any quote on the page. All the care taken over the percentage
was worth nothing while these were public.

The page never used them. Both constants were dead code in the browser: prices
come from the rates endpoint, already marked up. They are in `pricing.py` now,
server side, and the controller imports them instead of parsing its own source.

`STEEL_DENSITY` stays in the JavaScript, because the page genuinely uses it to
show spring weights and the server must charge for the same pounds of steel the
page displayed - so there is one copy and the controller still reads it from
there. A density is physics and tells a competitor nothing.

### The first check was the wrong check

Grepping the served bundle for "4.99" reported it still present after the move.
It was not: the bundle is 2 MB of every frontend module, and those digits were
SVG path coordinates in somebody else's icon. Scoping the search to our module's
own 49,601 bytes - between its `odoo.define` and the next one - showed all six
probes absent.

A naive substring search over a shared bundle produces false positives in
proportion to its size, which is the third time this session that a measurement
needed checking before its answer was believed.

## The margin objective had a degeneracy, capped (2026-10-07)

Choosing the slope for margin was right and incomplete. The margin is a distance
in frac, frac lives in [0, 1), and nothing stopped a line from earning credit for
sitting three units outside that band - at which point it is not separating
readings by their fraction at all, it is separating them by their floor with the
fraction playing no part. The reward grows with the slope, so the scan ran to
whatever bound it was given.

Measured rather than suspected:

| | before margin | margin, uncapped | margin, capped |
|---|---|---|---|
| lines with abs(b) > 0.1 | 0 | 16 | 3 |
| max abs(b) | 0.0385 | 0.2500 | 0.2500 |
| median abs(b) | 0.0010 | 0.0070 | 0.0070 |

**16 of 136 lines sat exactly on the scan bound**, at a slope 250 times the
median, and moving the bound from 0.25 to 1.0 moved all 16 with it - so they had
no interior optimum at all. Capping the margin at 1 leaves 3, and ties at the cap
fall through to the existing preference for the flattest line.

| | uncapped | capped |
|---|---|---|
| five-fold holdout | 90.16% | **90.21%** |
| in sample | 7863/8107 | **7865/8107** |
| validation clean length | 94.9% | 94.9% |
| validation flagged length | 75.9% | **76.5%** |

Clean accuracy unchanged, flagged up half a point, no holdout fold worse. The
accuracy is the smaller half of why it is worth having: **a fitter that walks to
the edge of its own search space is telling you the objective is wrong**, and it
was. A group that really does switch on its floor has `splitByCount` for exactly
that, fitted as a floor boundary rather than smuggled in as a near-vertical
threshold - and the 3 that remain are two-level rules at 3 and 4 springs, which
is what a genuine floor step looks like.

### Why two springs is the weak count, structurally

Surveying the level sets in the shipped table answers a question the accuracy
table only hinted at:

| spring count | groups | with three or more levels |
|---|---|---|
| 1 | 31 | 0 |
| 2 | 38 | **17** |
| 3 | 38 | 1 |
| 4 | 35 | 0 |

**Two springs is the only count whose rules have to choose among more than two
levels**, because it is the only count whose grid is mixed - 1 spring is whole
inches, 3 and 4 are whole plus a quarter, and 2 is either. More levels means more
boundaries, and every boundary is somewhere a new door can fall on the wrong
side. That is the structural reason behind 96.1% at two springs against 100% at
four, and it is not something a better threshold can fix.

Also from that survey: 134 of 142 level sets are expressible as
`inch (0 or 1) + quarter (0 or 0.25)`. The eight that are not involve negative
bonuses. That is the next thing worth testing - whether those are two independent
decisions rather than one ordered stack.

### And the line budget, re-measured against the new fitter

`LINE_SLACK` says how wrong a line may be before its group falls back to a band
table. It had been set twice against a fitter that no longer exists, so it was
swept again:

| LINE_SLACK | bands | five-fold holdout |
|---|---|---|
| 0.12 | 48 | 90.21% |
| 0.15 | - | 90.22% |
| **0.18** | **31** | **90.31%** |
| 0.20 | - | 90.26% |
| 0.25 | - | 90.18% |

A gentle plateau at 0.18-0.20 rather than a spike, and the whole range spans
0.13 points - **so this knob matters much less than it used to**, which is worth
knowing in itself. 0.18 is taken because the holdout prefers it and it carries 17
fewer memorised bands: on the external samples a band table scores 83-94% where a
line scores 96-97%, so moving groups off bands is the same direction the accuracy
moved.

Validation clean length 94.9% to **95.4%**, flagged unchanged at 76.5%. The tuned
samples slipped 98.1% to 97.9%, which is what less memorisation looks like on
samples that are partly in-sample for these knobs - and is the reason the
validation figure is the one quoted.

## Where the session ended up

| | start of session | now |
|---|---|---|
| validation clean length | 93.7% | **95.4%** |
| validation clean within 1" | 97.7% | **98.9%** |
| validation flagged length | 74.9% | **76.5%** |
| five-fold holdout | 89.63% | **90.31%** |
| bands / lines | 48 / 126 | **31 / 128** |

Better out of sample on every measure, and a smaller model. Nothing here changed
the physics: it was all in how a threshold is placed and when a group is allowed
to memorise instead.

## The bonus is not inch + quarter (refuted 2026-10-07)

The length bonus takes values in {0, 0.25, 1, 1.25} plus a few negatives, and 134
of 142 fitted level sets are expressible as `inch (0 or 1) + quarter (0 or 0.25)`.
The model treats them as an ORDERED STACK and fits one threshold per boundary. If
they were instead two INDEPENDENT decisions, each with its own threshold, the
model could predict a combination it had never observed - which is exactly the
failure in 3 of the 16 remaining clean misses, where the rule cannot produce the
level the reference used.

Tested by five-fold cross-validation within each group, on corpus readings only,
so neither the holdout nor the validation sample paid for the answer.

| | ordered levels | inch + quarter |
|---|---|---|
| all groups, 4495 readings | **93.73%** | 91.72% |
| 1 spring | **98.00%** | 96.59% |
| 2 springs | **86.97%** | 84.98% |
| 3 springs | **94.55%** | 91.48% |
| 4 springs | **95.78%** | 92.47% |

Worse everywhere, by 2 points. **The diagnosis is the useful part.** 103 of 142
groups have a CONSTANT quarter - one spring is always whole inches, three and four
always whole plus a quarter - so for those the sum form fits a second threshold
against a classification with only one class in it. That cut lands at an arbitrary
end of the data and then fires on a reading it never saw, inventing a quarter inch
from nothing. A free parameter that cannot help can only hurt.

Rescoped to the 38 groups whose quarter actually varies, all of them at two
springs, it is still worse: **77.95% against 76.65%**, ten readings over 771. So
the decomposition is refuted rather than merely mis-applied: the inch and the
quarter are not independent decisions.

Worth keeping from the attempt: those quarter-varying two-spring groups score
**78%** in within-group cross-validation against 94% for everything else. They are
the hardest part of the model by a wide margin, and they are hard because two
springs is the only count that has to choose a quarter at all.

## The slope grid is fine enough, and R1 comes back in (2026-10-07)

Two follow-ups to the margin objective, one negative and one that reverses an
earlier decision.

### A finer slope grid buys nothing

The threshold slope is scanned in steps of 0.0005. With margin as the objective
a finer grid could in principle find a slope with more room, so the step was
halved over the same range: **90.28% against 90.31%** on the five-fold holdout.
No gain, so the grid stays at 2000 steps. It is now a single named constant
shared by both fitters rather than a literal written twice, because a slope one
fitter can express and the other cannot would make the choice between their forms
depend on the grid rather than on the fit.

### R1 was excluded because of the fitter, not because of the data

Batch R1 is 380 readings chosen BECAUSE they land within 0.03 of a threshold the
model already used - the densest possible concentration at the boundaries. It was
held out on 2026-10-06 after costing a point of clean accuracy, under the heading
"dense is not diverse".

**That reasoning was about an objective that no longer exists.** The fitter then
minimised a COUNT of misclassified readings, and over-weighting one region really
does drag such a fit toward it. It now maximises the MARGIN of the threshold,
which depends only on the two readings either side of the cut - and readings
placed deliberately at a boundary are precisely what pins that down. So the
exclusion was re-measured rather than inherited:

| | R1 held out | R1 fitted |
|---|---|---|
| five-fold holdout | 90.31% | **90.49%** |
| validation clean length | 95.4% | 95.4% |
| validation clean within 1" | 98.9% | 98.9% |
| validation flagged length | **76.5%** | 75.9% |
| tuned-sample clean length | 97.9% | **98.6%** |
| bands / lines | 31 / 128 | 31 / 128 |

Including it now costs **nothing** on the figure that matters, where before it
cost a point. The holdout prefers it by 15 readings, the tuned samples by 0.7,
the never-tuned clean figure does not move, and never-tuned flagged loses a
single reading. The model is the same size either way. It is fitted again.

The result worth keeping is not the 0.18 points. It is that **"dense is not
diverse" was a statement about the fitter's objective and not about the data** -
the same readings that were poison to a count-minimising fit are neutral-to-useful
to a margin-maximising one. A batch held out for a measured reason deserves
re-measuring whenever the reason changes.

## The holdout lies when the corpus changes (and R1 goes back out)

**This retracts the commit before it.** Re-fitting batch R1 was justified on a
five-fold holdout that rose from 90.31% to 90.49%. That measurement was
confounded, and the confound is worth more than the result.

### What goes wrong

A reading marked `fit: false` is still SCORED by the holdout - that is the point
of keeping it. So moving a batch into the fit changes what the holdout fits AND
what it scores. A fitted batch gets same-batch neighbours in all four training
folds, so its own readings predict better, and the overall figure rises even if
every other door got worse.

Not a subtle effect. Re-fitting U5-U8 (1,522 readings) raised the holdout by
**0.88 points while the never-tuned validation sample fell by 2.3**:

| | U5-U8 out | U5-U8 fitted |
|---|---|---|
| five-fold holdout | 90.49% | **91.37%** |
| validation clean length | **95.4%** | 93.1% |
| validation clean within 1" | **98.9%** | 97.7% |
| validation flagged length | 75.9% | **80.2%** |
| tuned-sample clean length | **98.6%** | 95.1% |

The clean-for-flagged trade those batches were held out for is still there, and
the margin fitter did not absorb it - unlike R1, where it looked as though it had.

### Which forced a check of R1 itself

`dev/holdout-score.mjs` now takes `SCORE_EXCLUDE=R1`, which scores only readings
OUTSIDE the toggled batch and so holds the population fixed. That is the only
version of this number that answers "does that data help OTHER doors":

| scoring the same 7,728 non-R1 readings | |
|---|---|
| R1 held out | **90.515%** |
| R1 fitted | 90.463% |

**R1 in the fit makes other doors slightly worse**, by four readings. The entire
+0.18 was R1 predicting itself. On the validation sample its inclusion left clean
flat and cost a reading of flagged. So it has no measured benefit and a small
cost, and it is held out again - the table and corpus are byte-identical to the
state before that commit.

The original 2026-10-06 reasoning for excluding R1 was wrong about the mechanism:
it was the fitter's objective, not the density of the data. The conclusion
happened to be right anyway, which is the least satisfying way to be correct.

### The rule this leaves

**The five-fold holdout is only comparable between two models fitted on the same
corpus.** For every other change this session - the margin objective, the margin
cap, the line budget - the corpus was fixed and the holdout was sound. The moment
a change moves readings in or out of the fit, the holdout needs its population
pinned with `SCORE_EXCLUDE`, or it will congratulate the change for fitting the
data you just gave it.

## A second yardstick, and what it says about this session (2026-10-07)

`dev/eval-validation2-seed20261007.json` is a second 380-reading uniform draw
from the allowed box, pulled after every change below was already made, so
nothing has been tuned against it. 360 of the 380 returned an answer; 20 were
lost to non-JSON responses, spread evenly through the pull rather than clustered,
so not a session expiry.

The two draws are closely matched - both 175 clean readings, 187 against 185
flagged, same width spread - which makes them directly comparable:

| | seed 61006 | seed 20261007 |
|---|---|---|
| clean length | 95.4% | **93.7%** |
| clean within 1" | 98.9% | 98.3% |
| flagged length | 76.5% | **80.0%** |

**The first thing it bought was a correction.** A 1.7-point gap between two draws
of the same model, on 175 readings each, is 0.7 standard errors of the difference
- the draws agree. But it means the sampling error on a figure like this is about
**±1.7 points**, which is the same size as everything claimed this session. The
95.4% that has been quoted all day is the luckier of two draws; the honest central
estimate is **94.5%**.

### So the session's gain was measured properly, paired

Across-sample comparison is the wrong instrument. The right one is the same
readings scored by both models, which removes the sampling error entirely:

| 350 clean readings, both draws | |
|---|---|
| fixed by this session's changes | 10 |
| broken by them | 6 |
| net | **+4** |
| before / after | 93.43% / 94.57% |
| 16 discordant pairs, two-sided exact | **p = 0.454** |

And on the flagged half:

| 372 flagged readings, both draws | |
|---|---|
| fixed | 14 |
| broken | 8 |
| net | **+6** |
| before / after | 76.61% / 78.23% |
| 22 discordant pairs, two-sided exact | **p = 0.286** |

Pooled: 24 fixed, 14 broken, 38 discordant, **p = 0.143**.

**The accuracy gain from this session is not statistically demonstrated.** Ten
fixed against six broken is what noise looks like. The direction is consistent
across clean and flagged and across both draws, and pooling gets p to 0.14, which
is suggestive and no more. "93.7% to 95.4%, everything moved together" was a
single draw being read far too confidently, and the honest statement is **+10
readings in 722 at p = 0.14**.

### What does survive

- **The five-fold holdout**, 89.63% to 90.31%, is about +55 readings on ~8,100 at
  a fixed corpus. Far better powered than any of the above. It measures a
  different population - the corpus is mostly targeted batches rather than
  uniform draws - so it does not transfer directly to a quoted door, but it is
  real.
- **The model is smaller**: 48 bands to 31. That is structural and needs no
  statistics.
- **The degeneracy fix.** 16 of 136 lines sitting on the scan bound was a defect
  whether or not removing it moved a score.
- **The instruments.** Three measurement bugs found and fixed, two of which had
  been silently wrong for a while.

### The rule

A 175-reading subset cannot resolve a one-point change. Anything smaller than
about three points on a single draw has to be checked paired, on the same
readings, before it is believed - and ideally on two draws. Cheap to do, and it
would have caught this a lot earlier.

## Upstream error costs the length nothing, measured properly this time

With two never-tuned draws there are 350 clean readings to ask this of, and the
answer is unambiguous:

| across both draws | |
|---|---|
| length misses with the rung right | 16 |
| of those, with an EXACT TIPPT | **16** |
| readings whose TIPPT is WRONG | 8 |
| of those, length still right | **8** |

So a wrong TIPPT costs the length **0% of the time**, and no length miss coincides
with one. The D800-120 multiplier surface - 4.8% exact, worst error 1.7e-03, about
twenty times what it takes to move a rounded TIPPT - **cannot be what is wrong
with the lengths.** That lead is closed, now on twice the data that first
suggested it.

There is a reason, and it is a property of the margin objective worth naming.
A threshold placed midway between the two readings that straddle it is as far from
both as the data allows, so a small error in the active length moves a reading
within its own slack rather than across a boundary. **Maximising the margin bought
tolerance to upstream error**, not just better placement - which is why eight
readings with the wrong TIPPT all still land on the right inch.

## Where the thresholds are least pinned

The margin is the uncertainty: the cut sits midway between the nearest reading
either side, the true boundary is somewhere in that gap, and a new door landing
inside it is a coin flip. So the expected number of new doors a group gets wrong
is about `traffic x gap`, and both halves come from training data only - the
corpus for the gap, the U1-U4 uniform batches for traffic. Nothing in this ranking
touches either validation draw, which matters: the misses are KNOWN from those
draws, and picking where to pull by looking at them would quietly spend the
independence they are kept for.

The ranking says something I did not expect. The worst groups are not the
heavily-sampled ones:

| group | corpus readings | gap |
|---|---|---|
| 0.49/0.3938 at 3 springs | 6 | 1.00 (unpinned) |
| 0.4687/0.375 at 2 springs | 4 | 1.01 (unpinned) |
| 0.283/0.2343 at 4 springs | 7 | 1.00 (unpinned) |
| 0.3065/0.2437 at 4 springs | 38 | 0.16 |
| 0.3065/0.2437 at 3 springs | 31 | 0.18 |

A gap at the cap means no reading constrains that threshold at all within the
range a fraction can occupy. **The model's weak spots are groups of two to seven
readings**, not the ones with hundreds.

### But a rare group is rare for both of us

Generating candidates in the twelve worst groups returned **nothing for eight of
them**: a random orderable door essentially never lands there. That is the same
reason they have four readings in the corpus - and it also caps what pinning them
is worth, because a door that never arrives cannot be got wrong. The
`traffic x gap` ranking overstated them, since a traffic estimate built on two or
three uniform readings is mostly noise and the gap had hit its cap.

Re-aimed at the groups that do get traffic, five of them yielded 353 candidates
within 0.06 of a threshold. Those five carry about 13 expected wrong doors per
1,164 uniform readings - roughly 1% - which is the honest ceiling on this
particular pull.

## The three corpus flags, in one place

A reading in `dev/corpus.json` can carry three flags, and they mean different
things. They have each been explained where they arose, which is not where anyone
looks for them.

| flag | what it means | who ignores the reading |
|---|---|---|
| `flagged: true` | the reference answered with a message of its own | the LENGTH fit keeps the wire, drops the length |
| `fit: false` | measured to make the model worse | every fitter; `dev/replay.mjs` still asserts it |
| `dense: true` | sampled deliberately next to a fitted threshold | `fitStiffness` only |

**All three keep the reading.** Nothing is deleted - `dev/replay.mjs` asserts every
verified reading regardless, so a batch that is useless for fitting is still a
regression test. That is deliberate: a reading is an hour of somebody's polling and
a fact about the reference, whatever a fit currently makes of it.

`dense` is the newest and the most specific. It is **not a judgement about
quality** but about which fitter should see the data:

- Right for placing a threshold. That is what the reading was sampled for.
- Wrong for fitting `sMult`, which is per RUNG and shared by all four spring
  counts, and which `fitStiffness` fits by maximising a COUNT of readings whose
  snapped length comes out right. A boundary reading is the ambiguous kind, so a
  few hundred of them outvote the ordinary doors.

The numbers behind that: adding 353 boundary readings moved `sMult` on their three
rungs by up to 0.0073, which is **0.22" of active length on a 30" spring** - a
fifth of an inch of fraction, applied to every door on the rung including spring
counts the batch never touched. On a population held fixed with `SCORE_EXCLUDE`,
the holdout fell from 90.306% to 90.207% as a result.

`dev/import.mjs --dense` sets it at import time. Pass it for anything
`dev/frac-refine.mjs` generated.

## Why boundary-dense data poisoned the fit, and what fixing it bought

Two batches - R1 (380 readings, 2026-10-06) and P1 (353 readings, today) - were
both sampled deliberately next to a fitted threshold, and both made the model
worse. The second one was aimed much better than the first: at the CURRENT
thresholds, in the five groups with the widest gaps and real traffic, tripling
their density. On a population held fixed with `SCORE_EXCLUDE` it still cost 8
readings, 90.306% to 90.207%.

### The mechanism

Not the thresholds. **The rung's shared stiffness.**

`sMult` is fitted per RUNG and used by all four of its spring counts, and
`fitStiffness` picks it by maximising a COUNT of readings whose snapped length
comes out right. A reading sitting on a snap boundary is exactly the ambiguous
kind, so a few hundred of them outvote the ordinary doors:

| rung | sMult without P1 | with P1 |
|---|---|---|
| 0.3065/0.2437 | 0.98650 | **0.99375** |
| 0.4218/0.3437 | 1.01350 | **1.02100** |
| 0.283/0.2343 | 1.01550 | 1.01725 |

0.0073 on a 30" active length is **0.22"** - a fifth of an inch of fraction,
applied to every door on the rung including spring counts the batch never
touched. Only the three targeted rungs moved; the other 47 were untouched. That
is the whole transmission path.

### The fix, and what it is worth

Boundary-dense readings now carry `dense: true` and reach the band and threshold
fitters but not `fitStiffness`. After it, none of the three P1 rungs' stiffness
moves at all.

| same 7,728 scored readings | |
|---|---|
| dense in the fit, thresholds only | **90.554%** |
| dense out of the fit entirely | 90.515% |
| dense in the fit, unprotected (measured earlier) | 90.207% |

So protecting `sMult` turns -8 readings into +3, an eleven-reading swing that
confirms the mechanism. **But +3 of 7,728 is nothing**, and on the two
never-tuned draws clean length does not move at all (95.4% and 93.7%, both
unchanged) while flagged goes -0.6 on one draw and +1.6 on the other. The honest
summary is that boundary data is now **harmless rather than helpful**.

It is kept anyway, for reasons that are not about today's points: 733 real
readings re-enter the fit instead of being discarded, a sampling pattern that
will recur is no longer a trap, and the direction is positive rather than
negative. The ceiling was known before the pull - those five groups carry about 13
expected wrong doors per 1,164 uniform readings, so even a perfect fix was worth
about 1% - which is why this was measured on the holdout rather than on the draws
that cannot resolve it.

### What it says about the residual

Threshold placement in one group does not limit accuracy on doors in other
groups, and pinning a boundary does not transfer. 13 of 16 clean misses are
placement errors, spread about one apiece across many groups, each wanting its
own data. That is why the margin objective helped and more data does not:
**margin extracts more from the readings a group already has**, while new readings
only help the group they land in.

Which also makes `fitStiffness` the obvious next target. It is still scoring a
count, with plateaus, taking the lowest of a tie - the same three weaknesses the
threshold fitters had before today, and the only remaining parameter that reaches
every door on a rung rather than one group.

## Where "choose for margin" pays, and where it does not (2026-10-07)

Four selections in `dev/derive.mjs` picked the first of a tie. All four were
changed to prefer the candidate with the most room, and the results are not
uniform - which is more useful than if they had been:

| what is being chosen | effect on the fixed-population holdout |
|---|---|
| single-threshold **slope** | **+0.3 points** |
| multi-cut DP **slope** | **+0.2 points** |
| cut **position**, for a fixed slope | no-op - derived table byte-identical |
| bonus **ordering** in fitLineOwnSlopes | no-op - 13 rungs changed, accuracy identical |
| **`sMult`**, the rung's stiffness | **-7 readings**, reverted |

**The rule is not "maximise margin". It is "maximise margin when choosing a
boundary whose position the data only brackets".**

- The two slopes qualify: the data admits a range of lines, nothing distinguishes
  them on the readings seen, and the middle of that range is the minimax guess.
  Both paid.
- The cut position was already the midpoint between the two straddling readings,
  so there was nothing left to win. The honest outcome of that experiment was a
  byte-identical table, and it was reverted rather than shipped as a no-op with a
  comment claiming a benefit it did not have.
- The bonus ordering changed 13 rungs' tables and not one scored reading. Also
  reverted: rewriting a third of the table for no measured effect is churn.
- **`sMult` is not a boundary.** It is a physical scale, and where a reading falls
  inside its grid cell is determined by the spring, not by noise. Preferring the
  multiplier that centres readings in their cells fits a property the reference
  does not have, and it cost 7 readings. The plateau is still broken by taking the
  lowest multiplier that achieves it - arbitrary, and measurably better than the
  principled-sounding alternative.

With this done, **every selection in the fitter either has a measured tie-break or
is deliberately simplest-first.** The fitter-side ideas are exhausted; what is left
is data.

## sMult is absorbing something real, and it is not the divider formula

`sMult` is a per-rung multiplier on the active length. If the formula were exactly
the reference's it would be 1.000 everywhere. It is not: it runs 0.9745 to 1.0470,
**averages 1.18% away from 1.000, and only 9 of 50 rungs are within 0.1%**. Fifty
fitted constants hiding one missing term would explain placement errors everywhere
at once, so it is worth knowing whether that is what they are.

**They are not random.** sMult correlates with the outer spring's share of the
divider sum at **r = -0.66** across the 50 rungs, and with the wire ratio at -0.63.
Within each inner-wire family the needed correction falls monotonically as the
outer wire grows:

| inner wire | outer wire -> correction the formula still needs |
|---|---|
| 0.2253 | 0.2625 -> 1.046, 0.273 -> 1.012, 0.283 -> 0.985 |
| 0.283 | 0.3437 -> 1.019, 0.3625 -> 0.981 |
| 0.3938 | 0.4687 -> 1.046, 0.49 -> 1.009, 0.5 -> 0.997 |

So the model's dependence on the OUTER wire is slightly too strong. That is a
specific, checkable claim, and none of the obvious corrections is the answer.

### What was tried, on 6,454 readings with a reported TIPPT

Measured as the SPREAD of the still-needed correction across rungs - lower means
one formula fits every rung, which is what a right formula looks like:

| | spread |
|---|---|
| **shipped: `d^5 / (ID + d)`** | **1.824%** |
| `d^4.95`, `d^5.05`, `d^4.9`, `d^5.1` | 1.97%, 2.25%, 2.46%, 3.13% |
| `d^5 / (ID + 2d)` | 2.354% |
| `d^5 / ID` | 2.091% |
| `d^5 / (ID - d)` | 2.953% |
| `d^4 / (ID + d)` | 7.517% |
| unequal lengths: `A/(L+1) + B/L = TIPPT/springs` | 1.974% |

**The shipped formula beats every variant**, and the exponent 5 with `(ID + d)` is
a local optimum in both directions. The unequal-length quadratic is worth singling
out because it looked compelling - the outer spring is one inch longer than the
inner on all 6,454 readings, and our formula assumes they are equal - and it is
worse.

Two-parameter searches do reduce the spread, and should not be believed:
independent exponents reach 1.43% at `p_o=5.1, p_i=4.9`, a 22% reduction bought
with two more constants. And the outer ID "improves" monotonically as it rises -
6.5" fits better than 6.0" - which is the signature of a parameter absorbing error
rather than correcting a mistake, since nothing stops it going further.

### Where that leaves it

The per-rung correction is systematic, it depends on how the two springs split the
load, and it is not an exponent or a diameter convention. The remaining candidates
need information this data cannot supply: a coupling between the two nested springs
that our parallel-sum ignores, or a catalogue lookup rather than a closed form.

**Do not re-run the exponent search.** It has been done over a 6-by-5 grid plus
five diameter conventions, and the shipped values win.

## Boundary data: the third and last refutation

Batch P1's transfer test said +3 readings of 7,728 - nothing. But that test used
`SCORE_EXCLUDE` to score only readings OUTSIDE the batch, which answers "does this
help OTHER doors" and **deliberately excludes the population most likely to have
improved.** Real doors land in those groups too. So the question was re-asked
properly, on the two never-tuned draws, which are independent of P1 and contain
readings in its groups:

| clean readings from both draws | n | before | after | fixed | broken |
|---|---|---|---|---|---|
| IN a group P1 pinned | 14 | 12/14 | 12/14 | **0** | **0** |
| outside those groups | 336 | 319/336 | 319/336 | **0** | **0** |

Not one reading changed, anywhere.

**The in-group test is underpowered and that should be said plainly.** Only 14 of
350 clean readings land in those five groups, with 2 misses among them, so it could
only have registered an effect by flipping one of those 2 or breaking one of the 12.
A null there is consistent with no effect and could not have detected a small one.

What makes it conclusive is the agreement of three independent measurements, one of
which is well powered:

- transfer, 7,728 readings at a fixed population: **+3**
- the whole holdout: **unchanged**
- in-group, 350 never-tuned readings: **0 of 14**

So: boundary-dense data does not help the groups it lands in, does not help other
groups, and before the `dense` flag it actively hurt by dragging the rung's shared
stiffness. Three batches and two pulls have now tested this from every angle
available. **It is finished as an idea.**

### Which leaves exactly one lead worth having

`sMult` is absorbing something real - 1.18% of active length on average, which is
about 0.35" on a 30" spring, the same order as the placement errors being chased.
It is systematic (r = -0.66 against the outer spring's share of the divider sum)
and it is not an exponent, a diameter convention, or the unequal-length coupling.

Everything else is exhausted: every fitter selection now has a measured tie-break
or is deliberately simplest-first, upstream error costs the length nothing, more
data in a group changes nothing, and the per-group model class has been pushed as
far as its own cross-validation allows. **Finding the term sMult stands in for is
the only route left that could move accuracy by more than noise**, and it needs an
idea about the mechanism rather than more readings.

## The end-coil term, and why it is kept despite the draws (2026-10-07)

**The single-spring formula was missing its end coils, and the Duplex path still
was.** A torsion spring's rate uses its ACTIVE coils; the coils seated in the cone
at each end do not flex, so the wound length is the active length plus `e*d`, with
`e = 5` for an ID at or under 4.5" and `3` above. Those constants were already in
the file, used by the Single path only.

Verified against the reference's own figures on 477 single-spring readings:

| predicting a single spring's length | mean error | sd | worst |
|---|---|---|---|
| `divider/IPPT` alone | **+1.235"** | 0.354" | 2.447" |
| `+ e*d`, with the 5/3 rule by ID | **-0.001"** | **0.073"** | 0.141" |

A flat `e` is worse at every value tried (3, 4, 5, 6), so the split by ID is the
reference's rule and not a parameter chosen here.

For a nested pair the two springs share the shaft and turn together, so their RATES
add - but each rate is over its own active length, and the two differ by more than
the inch their wound lengths do, because they lose different amounts to their ends:

    A/a_outer + B/a_inner = TIPPT / springs
    a_outer = a_inner + 1 + e_inner*d_inner - e_outer*d_outer

a quadratic in `a_inner`. Summing the dividers over one shared length - what this
model did - is that equation with every end coil zeroed. On 6,454 readings the
omission biases predicted TIPPT by **-3.39%**; with the end coils it is +0.69%.
That is most of what the comment beside `sMult` meant by "the computed stiffness is
wrong by up to 4.6%" - 4.6% is what `e*d` comes to.

### The measurements disagree, and that is reported rather than resolved

| | |
|---|---|
| five-fold holdout, fixed population | 90.554% -> **90.890%** (+26 readings) |
| sMult spread across rungs | 1.512% -> 1.473%, rungs within 0.1% of 1.000: 9 -> 12 |
| never-tuned draws, PAIRED | 5 fixed, 7 broken, **net -2**, p = 0.774 |
| seed 61006 clean length | 95.4% -> 92.6% |
| seed 20261007 clean length | 93.7% -> **95.4%** |

The holdout gains 26 readings on 7,728 and is the better-powered measure; the two
draws move 2.8 points in opposite directions and their paired difference is noise.
**The never-tuned draws do not confirm this change.**

It is kept, and the reasons are not statistical. It adds **no parameters** - `e` and
the 4.5" threshold were already in the file. It is verified to 0.073" on 477
readings elsewhere in the same model. And a term that is physically present cannot
be "fitting" anything, which is the risk that made the sMult margin change wrong
even though it sounded more principled. A correct base formula asks less of a fitted
constant, and that matters most for the sparse rungs where `sMult` is least
determined.

What it does not do is close the gap. sMult still spreads 1.47% across rungs, so end
coils are part of what it absorbs and not all of it.

## The manufacturer's catalogue confirms the physics (2026-10-08)

The owner found https://resources.sscorp.com/door/catalog/SSC_Catalog.pdf, 140
pages. It does not give the Duplex rule, but it settles the single-spring formula
from the manufacturer's own documents rather than from our fit.

### Its own worked example

> "1PR .250 x 2 x 32" installed on a 7' door with a 15" radius, 400-8 drums.
> **IPPT is 41.5 per spring**, multiplier is .2866. Total IPPT of 83 divided by
> .2866 = 289 lbs door weight."

And its own rule for coils: **"COIL NUMBER x WIRE SIZE = SPRING LENGTH"**, so a
32" spring of .250 wire has 128 coils. Working backwards from IPPT 41.5:

| | |
|---|---|
| our formula with every coil active | 39.89 (**-3.9%**) |
| active coils implied by IPPT 41.5 | 123.04 |
| dead coils, 128 - 123.04 | **4.96** |
| our formula with 5 dead coils | **41.51 (+0.03%)** |

Five dead coils, from the manufacturer's arithmetic. That also confirms
`G = 30,000,000` and `TORSION_CONSTANT = 10.2`, neither of which had an
independent check before.

### And its published rate table

Six rows of the 2" ID stock table, against our formula with 5 dead coils:

| wire | length | catalogue IPPT | ours | error |
|---|---|---|---|---|
| 0.2070 | 22.00 | 24.2 | 24.16 | -0.17% |
| 0.2070 | 22.50 | 23.6 | 23.60 | -0.02% |
| 0.2187 | 23.50 | 29.6 | 29.60 | +0.00% |
| 0.2187 | 24.75 | 28.0 | 28.04 | +0.13% |
| 0.2187 | 26.00 | 26.6 | 26.63 | +0.11% |
| 0.2253 | 24.50 | 32.8 | 32.83 | +0.08% |

The catalogue only stocks 1 3/4" and 2" IDs - anything larger is made to order -
so it cannot settle the dead-coil count for a 6" spring. The reference's own
readings can, fitted per ID over 479 single-spring readings:

| spring ID | readings | dead coils | error at that count |
|---|---|---|---|
| 1.75, 2.625, 3.75, 4.375 | 387 | **5** | 0.07" |
| 5.25, 6 | 92 | **3** | 0.07" |

Which is exactly `LARGE_ID_THRESHOLD = 4.5` with `END_COILS_SMALL_ID = 5` and
`END_COILS_LARGE_ID = 3`. **The Single path is correct and now independently
confirmed from two directions.**

### Why the Duplex path still does not use it

Two nested springs turn together, so their rates should add, each over its own
active length, with their wound lengths an inch apart - which the data confirms on
all 6,454 readings. Written that way the predicted TIPPT is unbiased, +0.69%
against -3.39% without the end coils, **but its spread does not improve**: 2.78%
against 2.52%. An unbiased estimate with undiminished spread says the rates are
not simply adding.

It was shipped on the holdout (+26 readings) and withdrawn a day later: in sample
it cost **121 readings**, 82 fixed against 203 broken, concentrated on the
highest-traffic rung, and the two never-tuned draws moved 2.8 points in opposite
directions for a paired net of -2 at p = 0.774. Sweeping LINE_SLACK afterwards
(0.12, 0.18, 0.25, 0.32) recovers at most 16 of those readings, so the band knobs
were not the confound.

**So the lead is narrower and sharper than before.** It is not "find the term sMult
absorbs" in the abstract: the per-spring term is known, confirmed by the
manufacturer, and already correct in the Single path. What is missing is **how two
nested springs share a shaft**, and the 2.5% spread in the forward test is the
measurement of that ignorance.

## TIPPT is the door's REQUIREMENT, not the springs' output

The catalogue states it: *"REQUIRED IPPT equals Door Weight x Hi Moment Arm
divided by Number of Turns"*, and its worked example divides a total IPPT by the
drum multiplier to recover the door weight. Tested on 7,029 readings of every
assembly and drum:

| reported TIPPT / (door weight x drum multiplier) | |
|---|---|
| mean | **0.999537** |
| within 0.1% | **99.2%** |
| within 0.5% | 99.5% |

**So the reference's TIPPT is computed from the door, before any spring is
chosen.** That matters twice over.

### It explains a red herring

The "forward test" of the nested-pair coupling - predict TIPPT from the two
reported lengths and compare - carries a 2.5% spread that no parameterisation
would reduce. It cannot: it compares the rate the chosen springs DELIVER against
the rate the door REQUIRES, and the two differ by however far the length had to be
snapped onto the quarter-inch grid. On a 15" spring the ~1" effective grid is
worth 3%. The spread was measuring the grid, not the model, which is why dead
coils had no leverage on it at all (2.474% against 2.476%).

### And it reframes what sMult can be

The reference solves the same inversion we do: a required rate in, a length out.
If its Duplex path omits the end coils, then matching its OMISSION beats being
physically right - we are reproducing a calculator, not a spring. That is the best
explanation of why the end-coil term is exact for a Single spring, confirmed by the
manufacturer's own table, and measurably worse for a pair.

### The closed forms are exhausted

Every one of these was fitted against 6,454 readings and scored by the SPREAD of
the still-needed per-rung correction, because a right formula needs one correction
for every rung:

| | spread |
|---|---|
| **shipped: `(A+B)/TIPPT`** | **1.824%** |
| `+ 3*d_inner` | 1.768% |
| `+ 5*d_inner` | 1.817% |
| `+ 3*d_outer` / `+ 5*d_outer` | 1.841% / 1.954% |
| `+ 1"` / `+ 2"` | 2.087% / 2.721% |
| unequal lengths with dead coils | 1.632% |
| independent wire exponents | 1.426% (two free parameters, drifting) |
| wire exponents 4.6-5.3, four diameter conventions | all worse |

Nothing collapses it. The best figures come from parameters that drift to the edge
of whatever range they are given - an outer ID that keeps improving past 8", dead
coils that want to be 14 - which is a parameter absorbing error, not a mechanism.

**The remaining hypothesis is that their software carries a per-rung value**, which
is unfalsifiable from this data and is precisely what `sMult` already implements.
It would also match how `K` had to be handled: measured per rung by inverting the
reference's own cycle counts, not derived.

**So the sMult hunt is closed.** What came out of it is worth having - the
catalogue confirms G, the torsion constant, and the coil rule; the dead-coil count
is pinned per ID from 479 readings; TIPPT's origin is now known - but none of it
moves the length accuracy, and the residual there remains what it was: per-group
threshold placement, one miss apiece across many groups.

## The published wire chart validates the ladder, and the IDs we dropped

`SSC_SpringWireChart.pdf` from servicespring.com/resources is an image, so it has
to be read rather than parsed. Two things on it are worth having.

### The wire ladder is exactly right

All 41 sizes match `WIRE_SIZES` exactly, in both directions - nothing we offer is
missing from the chart and nothing on the chart is missing from us:

    .125 .135 .142 .1483 .1562 .162 .170 .177 .1875 .192 .207 .2187 .2253 .2343
    .2437 .250 .2625 .273 .283 .289 .295 .3065 .3125 .3195 .331 .3437 .3625 .375
    .3938 .4062 .4218 .4305 .4375 .4531 .4615 .4687 .490 .500 .5312 .5625 .625

Including the gap that matters: the chart goes **.192 to .207 with nothing
between**, which is the absence that cost a day's confusion when this model
offered a .200 the reference would never return. The ladder is now confirmed
against the manufacturer's own document rather than against inference from
switch points.

### And the IDs that are not sold

The chart's second table lists spring IDs with an "AVAILABLE FROM SSC" column:

| | |
|---|---|
| **stocked** | 1 3/4", 2", **2 5/8"**, 3 3/8", **3 3/4"**, 4 3/8", **5 1/4"**, **6"**, 7 5/8" |
| not stocked | 1 19/32", 1 13/16", 2 1/4", 2 7/16", 2 1/2", 2 3/4", 2 25/32", 3", **3 1/2"**, 3 25/32", 4", 4 1/2", 4 7/8", **5 1/2"**, 5 3/4", **5 7/8"** |

Every ID this module offers is stocked - the three Single sizes and both halves of
the one Duplex pair. **And every Duplex pair that was removed needed an ID that is
not:** the Raynor pair wants 3 1/2" AND 5 1/2", neither of them stocked, and the
Overhead pair wants 5 7/8". So those options were asking for springs the
manufacturer does not make, which is a better reason to have dropped them than the
one they were dropped for - that the model had never been calibrated for them.

### The drum limits are confirmed too, and they are PAIR figures

The catalogue's drum pages state a capacity **per drum**, and drums are "SOLD IN
PAIRS" - one each side of the door. So the door's limit is twice the printed
figure, and every limit this model carries matches on that reading:

| drum | catalogue, per drum | x2 | `DRUM_LIMITS` | max height |
|---|---|---|---|---|
| D400-96 | 265 | 530 | **530** | 8' = 96" ✓ |
| D400-144 | 375 | 750 | **750** | 12' = 144" ✓ |
| D525-216 | 750 | 1500 | **1500** | **19'-3" = 231"** ✓ |
| D800-120 | 1,100 | 2200 | **2200** | - |
| D575-120 | 500 | 1000 | **1000** | - |
| D525-54 | 500 | 1000 | **1000** | - |

All six exact. The D525-216's **231"** is the one worth pointing at: this model
carried 216" - the number in the drum's NAME - until the reference's own drum
record said otherwise, and every door between 217" and 231" was getting a
shortened spring until that was fixed. The catalogue confirms 19'-3"
independently, which is the second source that correction never had.

Worth keeping in mind for any future limit: a capacity printed on a drum page is
per drum, and the calculator's weight is the whole door.

## More uniform data does not help either, even filtered (2026-10-08)

U1-U4 bought 2.3 points of clean accuracy. U5-U8 cost 2.3 and was held out, with
the diagnosis that **half of a uniform draw is flagged**, and although flagged
readings already lose their lengths, their pairing and cycle count still move `K`
and so change rung selection for ordinary doors.

That diagnosis is testable without pulling anything: re-enable only the **clean**
794 of those 1,522 readings and leave the flagged 728 out entirely.

| | clean-only U5-U8 |
|---|---|
| five-fold holdout, 6,206 readings at a fixed population | 91.653% -> **91.814%** (+10) |
| never-tuned draws, CLEAN, paired | 6 fixed, 9 broken, **net -3**, p = 0.607 |
| never-tuned draws, FLAGGED, paired | 1 fixed, 5 broken, **net -4**, p = 0.219 |

**The diagnosis was right and the conclusion does not follow.** Filtering the
flagged half does turn a 2.3-point loss into roughly nothing - so the flagged
readings really were the damage - but what is left over does not help. The holdout
gains 10 readings on the corpus population while both halves of the never-tuned
draws lose, which is the same shape as the R1 refit: a change that suits the
corpus and not a door someone would actually quote.

### So the pull campaign is not worth running

This WAS the pull, in every sense that matters. U5-U8 is 1,522 readings drawn
uniformly from the allowed box, already paid for, and 794 of them clean. If those
do not move the figure, another 400 drawn the same way will not either, and the
rate limit is someone else's server.

With that, every avenue tried in two days of this is closed:

| | |
|---|---|
| boundary-dense data | refuted three ways - transfer, whole holdout, in-group |
| more uniform data | no gain, clean-only or not |
| fitter selections | every one has a measured tie-break or is deliberately simplest-first |
| the sMult term | per-spring physics confirmed by the manufacturer; the pair coupling resists every closed form |
| upstream error | costs the length nothing - all 16 misses have an exact TIPPT |

**~94.5% clean length is where this lands.** The residual is per-group threshold
placement, about one miss apiece across many groups, each needing data from a
group a random door rarely visits. That is a property of reverse-engineering a
black box from the outside, not a bug waiting to be found.

## Single, measured where it had never been measured (2026-10-08)

Single had been reported as 100% on everything - every spring ID, drum, spring
count, cycle target, radius, lift type and height. That was true of the data
and badly oversold, because `dev/eval-single.json` is not balanced:

| slice | clean readings | what "100%" rested on |
|---|---|---|
| hi-lift | **6** | one drum, one spring ID, two hi-lift amounts |
| 525-54HL, D800-120 | **0** | never drawn for Single at all |
| doors over 12 ft | 33 | thin above 15 ft |

Six readings give a Wilson interval of +-19.5 points. "100% of 6" and "100% of
123" print identically and mean nothing alike, which is why
`dev/single-breakdown.mjs` now prints the interval next to every slice.

Two draws filled the holes - `dev/single-gap-sample.mjs`, seeds 20261008 (200
cases, hi-lift) and 20261008001 (120 cases, tall standard). Pooled with the
original, 558 readings and 275 clean:

| | n | wire | length | within 1" | weight |
|---|---|---|---|---|---|
| all clean | 275 | **99.6%** | 100.0% | 100.0% | 100.0% |
| the three IDs sold | 216 | 99.5% | 100.0% | 100.0% | 100.0% |
| hi-lift (was 6) | **36** | 100.0% | 100.0% | 100.0% | 100.0% |
| 525-54HL (was 0) | 11 | 100.0% | 100.0% | 100.0% | 100.0% |
| D800-120 (was 0) | 11 | 100.0% | 100.0% | 100.0% | 100.0% |
| 12-14 ft | 63 | 98.4% | 100.0% | 100.0% | 100.0% |

Length and weight are still exact on all 275. Hi-lift is still exact, now on 36
readings across three drums and 12"-118" of lift rather than 6 on one drum.

### The one wire miss, and why it is the floor

`single-tall 117` - D400-144, 5 1/4", 3 springs, radius 15, 12 ft, 750 lb,
10,000 cycles. The reference picks 0.3065; we pick 0.295.

Our own cycle estimate at 0.295 is **10000.019** against a target of 10000.
Nineteen parts per million. We accept the smaller wire, the reference rejects
it, and nothing about the selection rule is wrong - the rule is "smallest wire
reaching the target" in both.

The obvious next move is to claim our cycle formula runs high and scale it
down. It does not. Across 275 clean readings, ours/theirs has median **1.0007**
with 53.5% above 1.0 - centred, not biased. The +-2-4% spread is mostly the
reference ROUNDING its reported cycle count: this case returns "16000" where we
compute 16458, and 16458 rounded down to a round thousand is 16000.

So the estimate is already as centred as the data can show, and deciding this
reading correctly would need the reference's cycle formula to about 1e-5
relative. One reading in 275 sitting that close to a threshold is the
resolution limit, not a bug. **Do not calibrate a scale on it** - that is the
same mistake as the reverted `cycles-low` fix and the withdrawn Duplex end-coil
term, both of which were one or five readings wide.

## A hi-lift drum answers ONLY under hi-lift (2026-10-08)

`525-54HL`, `575-120` and `D800-120` return an HTML page, not JSON, for any
request with `lift=Standard`. Under `lift=HiLift` they answer normally.

| | standard lift | hi-lift |
|---|---|---|
| the three hi-lift drums | **0 of 48** returned JSON | **120 of 120** |
| D400-144, D525-216 | 15 of 15 | n/a |

This cost an hour, because a logged-out server also answers with HTML. 48 of
200 readings came back that way, starting at reading 123 and never recovering,
and the obvious diagnosis was an expired session - a diagnosis that survived
writing a re-login into `dev/pull.mjs`, which then re-authenticated five times
and failed five times. Two things should have stopped it sooner: the failures
were **not contiguous** (124 and 126 answered fine between 123, 125 and 127),
and one of the original cases replayed later still succeeded unchanged.

The real tell is in the cross-tab above, which takes one query. **When the far
end keeps serving HTML, suspect the REQUEST before the cookie.** The re-login
in `dev/pull.mjs` is still worth having, but it is capped at five for exactly
this reason: retrying an impossible request is just a slow way to hammer
someone else's server.

`dev/single-gap-sample.mjs` now draws standard lift only from drums that have
it, so the combination cannot be generated again.

## Five more Duplex hypotheses, all refuted (2026-10-08)

The open lead was the note in `duplexActiveLength`: sMult averages 1.18% off
1.000 and correlates with the outer spring's share of the divider sum, so
"whatever the real coupling is, finding it is the one lead left that could move
accuracy by more than noise". Five attempts on it. **Nothing shipped, accuracy
unchanged.** Each one is written down because each is a query someone will
otherwise run again.

### 1. The error is NOT upstream - proved from the reference's own numbers

The reference reports `totalInchPoundPerTurn`, `turnsOnSprings` and
`multiplier` on every reading, so our chain can be checked link by link
instead of only at the end. On the two never-tuned draws, 347 clean modelled
readings with the wire agreeing:

| | on the 331 exact | on the 16 misses |
|---|---|---|
| TIPPT matches | 97.6% | **100%** |
| turns matches | 99.1% | **100%** |
| multiplier matches | 93.4% | **100%** |

Upstream is *perfect* on every miss and imperfect on the readings we get right.
That is the opposite of a confound and it settles the question: the whole error
is in S, and the S the reference implies is 0.957-1.038 times ours.

This also re-confirms `dev/mult-survey.mjs`: the D800-120 hi-lift multiplier
surface really is inaccurate, and really does cost the length nothing.

### 2. sMult is NOT an additive dead-coil term in multiplicative clothing

The tempting story: dead coils add `dead * wire` to a length, the model
multiplies instead, so one constant per rung cannot fit both short and long
springs. It predicts an intercept.

Per rung, regressing the reference's length on `x = springs/TIPPT` over 4,486
deduped readings, 31 rungs:

- intercepts land between **-0.54 and +0.82**, scattered around zero, against a
  predicted `5*dIn` of **1.13 to 1.81**
- a free intercept improves pooled RMS from 0.3243 to 0.3177 - **2%**
- free slopes straddle the computed A both ways, ratio 0.977 to 1.053

So sMult is a genuine multiplicative per-rung scale. The additive story is dead,
which is consistent with the end-coil term having been withdrawn once already.

### 3. The residual has no structure left in it

Pooled residual around the per-rung line, 4,486 readings, RMS 0.3177":

| against | r |
|---|---|
| turns | -0.005 |
| turns * inner wire | -0.004 |
| predicted length | 0.000 |
| door height | 0.050 |
| hi-lift | 0.054 |
| spring count | 0.159 |

and the RMS is flat - 0.29 to 0.33 in every spring-count band and every turns
band. **0.3177 is what rounding to the inch produces** (1/sqrt(12) = 0.289), so
the line already explains the physics and the residual is the snap. There is no
missing term to find by regression, which is why four sessions of looking for
one came back empty.

### 4. The grid is {k, k+0.25}, and the quarter inch is a spring-count rule

Over the same 4,486, the fractional part of the inner length is **only ever .00
(52.6%) or .25 (47.4%)** - never .5, never .75. And it is nearly deterministic:

| springs | n | share with .25 |
|---|---|---|
| 1 | 1208 | **0.0%** |
| 2 | 1649 | 30.3% |
| 3 | 1032 | **100.0%** |
| 4 | 597 | **100.0%** |

Inner and outer always agree on the fraction (100%) and the pair is always
exactly 1.00" apart (100%).

This looked like a free fix for ten minutes. **The model already reproduces it
exactly** - 100%, 99.0%, 100%, 100% agreement by spring count, disagreeing on
17 of 4,472 readings and on none that it otherwise gets right. The three-regime
rounding is already carrying this rule; checking before "fixing" saved a
regression.

### 5. One slope per rung cannot even reach where the model already is

With a single slope per rung and a nearest-grid snap, sweeping every slope that
any reading admits, the best achievable in sample is **4100/4486 = 91.40%** -
and three rungs reach 100% only because they have 12 to 19 readings. The model
is at 92-95% on never-tuned data with the fitted per-rung thresholds, so the
threshold machinery is extracting *more* than the clean closed form can. A
tidier model here would be a downgrade.

### Where that leaves it

Every link is now measured rather than assumed: upstream is exact on the
misses, the shape is multiplicative not additive, the residual is structureless
at the grid scale, the grid and its quarter-inch rule are known and already
reproduced, and the simple closed form is worse than what ships. The
`~94.5% clean length` conclusion stands, and now stands on five refutations
instead of an absence of ideas.

What would actually move it is not another fit. It is the reference's own rule
for S - a published duplex rate table, or a reading where the two springs'
coupling can be observed directly rather than inferred through a rounded
length.

## Per-rung data volume IS causal, and that reopens the pull (2026-10-08)

Every previous lead was about the SHAPE of the length model. This one is about
how much data each rung has, and it is the first thing in many sessions that
measures as a real, causal effect on never-tuned data.

### The observation

On the never-tuned draws, split the 347 clean readings by how many length
readings their rung has in the corpus:

| rung's corpus length readings | never-tuned readings | exact |
|---|---|---|
| 300+ (four rungs) | 121 | **100.00%** |
| under 300 (the rest) | 226 | 92.9% |

Zero misses in 121 if the true rate were 7.1% is p = 0.0001. But that could
just mean the well-covered rungs are the ones a random door lands on, and
therefore the easy ones.

### The experiment that settles it

`sh dev/rung-volume.sh`. Cap how many LENGTH readings those four rungs may
contribute, leave K alone so rung selection cannot move, and re-score **the
same 121 readings**. Random subsample, two seeds, mean:

| length readings per rung | exact |
|---|---|
| 40 | 87.60% |
| 80 | 90.50% |
| 160 | 92.56% |
| 240 | 97.52% |
| 320 | 98.35% |
| full (309-1199) | **100.00%** |

Monotone, still climbing at 320, on a fixed population, with nothing changed
but how much data the rung got. **Data volume per rung causes length
accuracy.** And the thin rungs show the same slope - starving the 42 rungs
under 200 readings gives 83.44% at 50, 88.96% at 90, 92.64% at 140 against
93.87% as they stand - so the curve is a property of the fit, not of those four
rungs.

### THE SEED MATTERS - the first version of this overstated the effect

Capping by corpus ORDER keeps the first N readings, and the corpus is in batch
order with the early batches deliberately boundary-dense. File-order capping at
120 reported 88.43%; a random subsample of the same size reports 92.56%. The
effect is real either way but a third smaller than first measured. Quote the
seeded numbers, and never subsample a batch-ordered corpus by slicing it.

### Why the U5-U8 result does not contradict this

a3002a7 re-enabled 794 clean uniform readings and measured net -3 on the
never-tuned draws, concluding more data does not help. Re-tested here, admitted
for the 42 thin rungs only, it moves 153/163 to 154/163 - one reading.

That is not a refutation, it is the dose-response being honest. Uniform data
lands on rungs in proportion to how often a door hits them, so it piles onto
the four rungs already at 100% and adds a **median of 14** readings to a thin
rung. All 42 are still under 300 afterwards. The previous conclusion was right
about the data it had and wrong to generalise: the allocation failed, not the
idea.

### Aiming at a rung is possible

The rung is an OUTPUT - the reference picks the wire pair - so a pull cannot
request one directly. But our own wire choice is right 99.1% of the time, so the
model is an adequate targeting system: sample geometries locally for nothing,
keep those it says land on the wanted rung and raise no warning, and pull only
those. 15,000 free local samples reach **every one of the 25 visited thin
rungs**, none unreachable, 55 to 411 candidates each.

### What it would cost

Bringing every rung a real door visits up to 320 length readings:

| budget | projected gain | time at 1 req/sec |
|---|---|---|
| 400 | +0.7 pts | 7 min |
| 800 | +1.2 pts | 13 min |
| 1600 | +1.9 pts | 27 min |
| 3200 | +3.0 pts | 53 min |
| 4624 (all of it) | **+3.5 pts** | 77 min |

which would put clean length near 98.9%. The projection interpolates the curve
above and assumes new readings inform a rung as much as the ones removed did -
the honest caveat, and the reason to run it in batches and re-measure rather
than all at once.

A 400-request pilot cannot be validated on its own: +0.7 points is under 3
readings of 347, which no paired test can resolve. The evidence for going ahead
is the starvation experiment, not a pilot.

## Per-spring-count stiffness: cross-validation said yes, the model said no (2026-10-08)

The campaign took the busy rungs from about 230 length readings past 320, and
more data can afford more parameters - so the per-rung sMult decision, made at
the smaller size, was worth re-opening. `STIFFNESS_REPORT=1 node
dev/derive.mjs` measures it. Over the 35 rungs with 40+ readings:

| | in sample | five-fold CV |
|---|---|---|
| one multiplier per rung | 6673 | 6551 |
| one multiplier per spring count | 6948 | **6831** |

An out-of-fold gain (+280) **larger** than the in-sample one (+275) is normally
the end of the argument: extra parameters that generalise are not overfitting.
The per-count multipliers also differ by real amounts - 0.273/0.2253 wants
1.00725, 0.99525, 1.014, 1.01725 across one to four springs, a 2.2% spread, and
2% of a 50" spring is an inch.

**Built properly it lost a reading.** Per-count multipliers in the table, the
component selecting by spring count, the bands refitted against the same
multiplier so nothing was scored under a value it was not fitted under: the
never-tuned draws went 340/347 to 339/347.

### Why the cross-validation was wrong

It scored ONE STAGE in isolation, and the stage below it already does that job.
`lineByCount` and `byCount` are keyed by spring count, so the thresholds were
already absorbing the per-count variation. The CV counted a gain the pipeline
already had, and paid for it with parameters.

The lesson generalises past stiffness: **a fitter stage cannot be scored on its
own when a later stage can compensate for it.** Only the whole pipeline,
against data nothing was tuned on, settles anything. That is the same mistake
shape as the five-fold holdout rising while the never-tuned draws fell during
the U5-U8 question - a number that improves because the fit suits the corpus,
not the door.

### One more near miss worth recording

Getting this wrong the first time cost 97.98% -> 83.00%, because `sMultByCount`
was fitted in `derive.mjs` but left out of the object the installer reads. The
bands were built on `rawActive * mFor(springs)` and the component still applied
the rung-wide `sMult`. That returned object is the ONLY channel between the
fitter and the model: a quantity that is not in it does not exist downstream,
and the failure is silent and total rather than loud and local.

## The CANIMEX rate chart: three formulas confirmed, the coupling closed (2026-10-08)

The owner found `idcspring.com/.../RCI3_75.pdf` - a **CANIMEX SPRING CHART**,
the same manufacturer as the drums, covering 29 wire sizes at 3.750" inside
diameter. Single springs only; no duplex, nested or concentric content anywhere
in its 1,899 lines. Four other links sent with it were compression-spring pages
or inaccessible (one 403 to both WebFetch and curl, one Scribd error page, two
covering compression springs only). One of them, Tokaibane, does state the
nested rule: concentric springs in parallel are **K = k1 + k2 + k3** with no
correction factor published anywhere.

### What it confirms, independently of the reference

| our formula | against the chart | agreement |
|---|---|---|
| `divider = 30e6*d^5/(10.2*(ID+d))` | published Rate x wire, 29 sizes | **1.7 parts in 10,000** |
| `cycles = (124205*d^2.79/torque)^4.67` | 145 published MIP values | mean ratio **0.9952**, sd 0.58% |
| `weight = density*(pi^2/4)*d*(ID+d)*L` | published weight per inch, 29 sizes | implied density constant to **0.01%** |

G = 30e6 and K = 10.2 were taken from the SSC catalogue; a second manufacturer
publishing the same thing settles them. The MIP agreement matters most, because
the cycle model is what produced the single Single wire miss, and it is now
checked against 145 values nobody fitted it to.

### Where SSC and CANIMEX actually differ, so this chart cannot correct us

Two constants, both differing in the same direction:

| | CANIMEX chart | SSC, as the model reproduces it |
|---|---|---|
| dead coils at 3.75" ID | **3** | **5** |
| steel density | 0.28320 lb/in^3 | 0.2836 |

The dead-coil one is not arguable: our Single path uses 5 and reproduces 275
never-tuned readings exactly, 65 of them at 3.75". At 3 every one would be
2 x 0.2253 = 0.45" short, far outside the quarter-inch grid. These are two
different houses' conventions and SSC's is the one being modelled.

### And the coupling question is now closed, not open

The withdrawn end-coil term assumed 5 inner / 3 outer. With dead coils FITTED
instead - two global parameters, which would replace fifty per-rung sMults -
over 6,748 clean duplex readings:

| dead coils, inner / outer | bias | spread |
|---|---|---|
| 0 / 0, what ships | -2.85% | 2.48% |
| 5 / 3, the withdrawn attempt | +1.25% | 2.48% |
| 3 / 3, CANIMEX published | +0.48% | 2.46% |
| **7 / 0, best of the whole grid** | -0.19% | **2.18%** |

Freeing both parameters buys 2.48% to 2.18%, and the optimum is physically
meaningless - seven dead coils on the inner spring and NONE on the outer. More
to the point, 2.2% of a 50" spring is 1.1 inches, larger than the 1" grid step
the model has to land on. **No choice of dead coils lets rate-addition reach the
grid.**

So rates do not add for these pairs, confirmed now with two free parameters and
6,748 readings rather than one fixed guess. The literature route is finished:
the published nested rule is the one that does not work here, and nothing in
these sources suggests another. What would still help is a duplex rate chart -
IPPT for a NESTED pair - and this document shows such charts exist in this
exact format, just not for pairs.

## The flagged half was refusals, not a weakness (2026-10-09)

`dev/clean-cases.mjs` has always reported two numbers - clean at about 95-98%
and flagged at about 79% - and the second one looked like the model falling
apart on half the population. It is not. Splitting flagged by what the
reference is actually complaining about, on the two never-tuned draws:

| class | n | wire | length exact | within 1" |
|---|---|---|---|---|
| clean | 350 | 99.1% | 98.0% | 99.7% |
| **warned but buildable** | 85 | 98.8% | **100.0%** | 100.0% |
| **ORDERABLE, both** | **435** | **99.1%** | **98.4%** | **99.8%** |
| refused by the reference | 286 | 99.3% | 73.9% | 89.1% |

Of 2,910 flagged Duplex readings the complaints are 1,426 wire past the inside
diameter's maximum, 1,251 assembly too long for the door, 1,111 spring over
120", 37 drum overloaded, 23 over max MIP - all refusals. The reference will
not build any of them, so the model's length there is not a quote, it is the
input to a warning. The genuinely orderable remainder is "only spring lengths
between 0 and 96 are recommended" and the short-cycle-life notes, and the model
gets **every one of those 85 readings exactly right**.

So the figure to quote for doors a customer can actually order is **98.4%
exact, 99.8% within an inch**, and the hard-looking flagged bucket was 97%
refusals. `dev/orderable.mjs` prints this split and `dev/honest.sh` now runs it.

## Wire selection is at its floor too (2026-10-09)

Length has had all the attention because it is where the misses are, but the
wire is chosen first and a wire miss is excluded from the length figure - so
three wire misses on the draws were never anyone's target. All three:

- have an **exactly correct TIPPT and multiplier**, so nothing upstream is wrong
- are **hi-lift at radius 15**, two on 525-54HL and one on 575-120
- sit within **0.2% of the acceptance boundary** - 0.9984, 1.0016, 1.0021 of
  target - and pull in OPPOSITE directions, so no scale correction fixes them

The rule itself was then tested on all 6,748 clean duplex readings, because a
rule chosen to fit three readings of the evaluation set is the mistake this
project keeps re-learning:

| acceptance rule | reference's rung reproduced |
|---|---|
| `exact >= target` (ships) | **99.50%** |
| `exact >= 0.998 * target` | 98.98% |
| `exact >= 1.003 * target` | 98.61% |
| `round1000(cycles) > target` | 92.29% |
| `round1000(cycles) >= target` | 89.98% |
| `ceil1000(cycles) >= target` | 82.84% |

The shipped rule is the best of the family by half a point, and the rounded
variants - tempting because "the reference computes from the figures it
displays" is a documented principle here, and it is why TIPPT is rounded to one
decimal - are seven points worse. Moving the threshold to catch two of the
three misses would cost about sixty readings elsewhere.

## A third never-tuned draw, and what it says about the first two (2026-10-09)

The two validation draws were getting spent. Each question checked against a
clean sample costs a little of its independence, and this session checked
several: whether to re-enable the held-out uniform readings, whether per-count
stiffness helped, whether the acceptance threshold should move, and the
rung-volume campaign was measured against them after every one of ten batches.
So: 400 fresh uniform cases, seed 20261009, drawn after all of it and used for
nothing before this measurement.

**The campaign's gain is confirmed on data nothing was tuned against.** Scoring
the pre-campaign table and the current one against this draw:

| on the fresh draw | pre-campaign | now |
|---|---|---|
| clean | 95.1% | **97.3%** |
| orderable | 95.6% | **97.4%** |
| within 1" | 100.0% | 100.0% |
| refused | 75.2% | 77.9% |

Paired on the 185 clean readings: 5 fixed, 1 broken, net +4, sign test
p = 0.2188 - the same direction and size as the spent draws showed, and
underpowered on its own at half their pooled size. Pooling all three gives 16
fixed against 3 broken, but draws one and two are partly spent so that
overstates the confidence; the honest statement is that the unbiased draw moves
+1.8 points on orderable doors and agrees in direction.

### The draws read about a point high, and now we know how much

| | orderable, exact |
|---|---|
| draws 1+2, used for every decision this session | 98.4% |
| draw 3, used for nothing | **97.4%** |

One point. That is what the monitoring bought, and it is why `dev/honest.sh`
now prints the newest draw first and labels it the one to quote. Not a large
bias - it is roughly the sampling error on 228 readings either way - but it is
in the direction theory predicts, and it is better measured than assumed.

**Within an inch is 100.0% of 228 orderable readings** on the fresh draw, which
is the figure that matters for a customer who can live with a quarter turn of
adjustment.
