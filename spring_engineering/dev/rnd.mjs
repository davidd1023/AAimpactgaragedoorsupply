// ONE seeded random generator for every sampler here.
//
// WHY THIS EXISTS, AND IT COST THE OWNER 400 REQUESTS ON SOMEONE ELSE'S SERVER.
//
// Five tools carried this same four-line block by copy:
//
//     let seed = Number(seedArg) || 1;
//     const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; ... };
//
// IT IS NOT AN LCG. `seed * 1103515245` reaches 2.4e18 and a double is exact
// only to 9.0e15, so the low bits are thrown away on EVERY step - not just a
// large starting seed, every step, because the state itself is up to 2^31. The
// sequence then falls into whatever short cycle that rounding lands it in, and
// the length of that cycle depends on the seed in a way nobody can predict.
//
// MEASURED over the 28 seeds this repository has actually used, distinct values
// in 30,000 draws:
//
//     seed 20261009      17,690      seed 61006         10,547
//     seed 202610081006  13,039      seed 202610081014  10,936
//     seed 202610081013     *318*
//
// Batch V13 drew on that last one. 30,000 sampled geometries collapsed onto a
// few hundred, so the 400 cases it bought held **21 distinct doors**; 379
// requests asked the reference the same questions over again. The accuracy
// score moved 97.53% to 97.53% and it looked like the corpus was saturated.
//
// THE FIX IS `Math.imul`, which multiplies as exact int32 and wraps - the
// arithmetic a C LCG does and the arithmetic these constants were chosen for.
// The same 28 seeds then give 30,000 distinct values out of 30,000, worst case.
//
// AND THE DIVISOR IS 2**31, NOT 2**31-1. Dividing by 0x7fffffff returns
// exactly 1.0 when the state hits its maximum, and `pick()` then reads one
// past the end of its array and hands back `undefined` - a case with no drum
// in it. One chance in 2^31 per call, which is a bug that waits for a campaign
// big enough to find it.
//
// NOTHING COMMITTED IS INVALIDATED. The eval-* draws are saved DATA, not
// re-generated, and they were checked: 380/380, 380/380 and 400/400 distinct.
// Every accuracy figure ever quoted off them stands. Only V13 was spoiled.
//
// The ref-state.mjs lesson, a second time: a thing that four or five tools each
// keep their own copy of will differ between them, and the copies will be
// wrong together in a way no single tool's tests can see. One copy, imported.

const A = 1103515245;
const C = 12345;

// A seeded generator. `seed` may be anything Number() accepts, including the
// long date-like strings the campaign scripts build.
export function makeRnd(seed) {
    let s = (Number(seed) || 1) >>> 0;

    const rnd = () => {
        s = (Math.imul(s, A) + C) >>> 0;

        return (s & 0x7fffffff) / 0x80000000;
    };

    return {
        rnd,
        pick: (a) => a[Math.floor(rnd() * a.length)],
        between: (lo, hi) => lo + Math.floor(rnd() * (hi - lo + 1)),
    };
}

// How many distinct values this generator yields from `seed` in `n` draws.
// Exported so a sampler can REFUSE to spend a budget on a degenerate stream
// rather than discovering it from the importer afterwards.
export function spread(seed, n = 30000) {
    const { rnd } = makeRnd(seed);
    const seen = new Set();

    for (let k = 0; k < n; k++) {
        seen.add(rnd());
    }

    return seen.size;
}
