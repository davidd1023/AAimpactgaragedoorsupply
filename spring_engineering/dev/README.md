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
