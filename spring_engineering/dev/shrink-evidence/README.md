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
