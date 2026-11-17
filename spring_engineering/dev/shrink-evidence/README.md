# Partial-pooling holdout evidence (2026-11-13)

`holdout-rows.tar.gz` holds the per-reading outcome of six five-fold holdout
runs over the whole corpus, one file per `SHRINK` value:

    shrink-0.rows     the shipped fit, no pooling
    shrink-10.rows    shrink-25.rows    shrink-60.rows
    shrink-150.rows   shrink-400.rows

Each line is `ROW<tab><reading id><tab>1|0` - whether that reading's wire AND
length were both right, scored **out of sample**, on the fold that withheld
it. Every reading appears exactly once per file.

## Why it is committed

It cost about three hours of compute and the container is ephemeral. The
result it supports is **not shipped** and needs one more confirmation run, so
the next session needs to be able to re-read the evidence rather than trust a
summary of it. 670 KB against a 14 MB corpus is proportionate.

## How to read it

    node dev/shrink-report.mjs <a.rows> <b.rows>

which pairs the two runs reading by reading and runs an exact McNemar test.
**Do not compare the totals directly** - fold-to-fold spread is 10.5 readings,
so a difference under about 21 is invisible that way, which is how the
LINE_SLACK screen of 2026-11-12 came to read noise as a finding.

## How to regenerate

    sh dev/shrink-sweep.sh 0 60              # five folds, about 70 minutes
    MOD=4 OUT=/home/odoo/logs/m4 sh dev/shrink-sweep.sh 0 60

The second is the confirmation under a different fold partition that was
still running when this was saved.

## The other tarballs

Each holds one five-fold run, to be paired against the baseline for its own
partition - `sl10-60.rows` for MOD=5, `sl4-60.rows` for MOD=4. **Never pair
across partitions**: a four-fold run trains on less, so its baseline differs
(12,018 against 11,966) and the comparison is only valid within one.

    holdout-rows-joint.tar.gz       POOL_JOINT, the refitted pooling target
    holdout-rows-slack.tar.gz       LINE_SLACK=0.10
    holdout-rows-mod4.tar.gz        the MOD=4 confirmations
    holdout-rows-sideslack.tar.gz   SIDE_SLACK=0.18, a wash (-5, p = 0.59)
    holdout-rows-formbycv.tar.gz    FORM_BY_CV=1, REJECTED (see below)

## FORM_BY_CV is a rejection, and the reason generalises (2026-11-17)

`fbc5-60.rows` is the five-fold run of `FORM_BY_CV=1`, which offers a split
as a third candidate to every line that accepts misses. Paired against
`sl10-60.rows`:

    12,938 readings   -19   27 fixed / 46 broken   p = 0.0344

Significantly **worse** - the shipped configuration wins. It is kept because
of HOW it misled: in-group, the seven groups that took the split beat their
line by +0.7 to +2.1 points, each a proper five-fold cross-validation over
100 to 467 readings.

**A cross-validated score is unbiased for a FIXED candidate; the MAXIMUM over
several is not.** Taking the best of line, split and bands inflates the
winner by whatever noise favoured it, and on groups that size the noise is a
point or two - precisely the margins seen. Only the outer folds, which
selected nothing, told the truth.
