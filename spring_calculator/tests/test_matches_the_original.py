"""THE DRIFT ALARM.

`spring_calculator` is generated from `spring_engineering` by
`tools/build_spring_calculator.py`. The whole reason it is generated rather
than copied is that **151 of the 288 commits** to the original in the 90 days
to 2026-11-02 touched the engine - so a hand copy is wrong within the
fortnight, and wrong silently.

These tests are what makes "re-run the script" a rule rather than a hope. They
fail the moment somebody changes the engine in `spring_engineering` and does
not regenerate, and the fix is always the same one command.

THEY SKIP WHERE THE ORIGINAL IS NOT INSTALLED, which is the second project -
there is nothing to compare against there, and a module that cannot run its
own tests on the machine it ships to is worse than one that quietly says so.
"""

import importlib
import pathlib
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

#: The repository root, three levels up from this file.
ROOT = pathlib.Path(__file__).resolve().parents[2]


def original():
    """`spring_engineering`'s engine, or None where it is not installed."""
    try:
        return importlib.import_module(
            "odoo.addons.spring_engineering.controllers.main")
    except ImportError:
        return None


def ours():
    return importlib.import_module(
        "odoo.addons.spring_calculator.controllers.main")


#: Specifications spanning what the page can actually be asked for: both wire
#: sizes the shop stocks for a single, one spring and two, the three visible
#: I.D.s, a 5 1/4" (which adds the plastic filler and so exercises a whole
#: second branch), hi-lift and both cycle ratings.
GRID = [
    {"assembly": "Single", "springs": 2, "doorWeight": 355,
     "doorHeight": "7' 0\"", "doorWidth": "9' 0\"", "hiLift": 0,
     "cycles": 25000,
     "springsSpec": [{"role": "Spring", "wire": 0.2625, "id": 6,
                      "length": 32.25}]},
    {"assembly": "Single", "springs": 1, "doorWeight": 180,
     "doorHeight": "7' 0\"", "doorWidth": "8' 0\"", "hiLift": 0,
     "cycles": 10000,
     "springsSpec": [{"role": "Spring", "wire": 0.2188, "id": 3.75,
                      "length": 28.0}]},
    # 5 1/4" takes a plastic filler, one per spring, cut to its own length.
    {"assembly": "Single", "springs": 2, "doorWeight": 520,
     "doorHeight": "8' 0\"", "doorWidth": "16' 0\"", "hiLift": 0,
     "cycles": 25000,
     "springsSpec": [{"role": "Spring", "wire": 0.3125, "id": 5.25,
                      "length": 40.0}]},
    # Hi-lift, which moves the drum and the turns.
    {"assembly": "Single", "springs": 2, "doorWeight": 410,
     "doorHeight": "7' 0\"", "doorWidth": "12' 0\"", "hiLift": 24,
     "cycles": 25000,
     "springsSpec": [{"role": "Spring", "wire": 0.2813, "id": 6,
                      "length": 36.0}]},
    {"assembly": "Single", "springs": 2, "doorWeight": 260,
     "doorHeight": "6' 6\"", "doorWidth": "9' 0\"", "hiLift": 0,
     "cycles": 50000,
     "springsSpec": [{"role": "Spring", "wire": 0.25, "id": 2.625,
                      "length": 30.5}]},
    # The refusals have to match too: a quote that comes back as an error in
    # one module and a price in the other is the worst possible drift.
    {"assembly": "Duplex", "springs": 2, "doorWeight": 355,
     "doorHeight": "7' 0\"", "doorWidth": "9' 0\"", "hiLift": 0,
     "cycles": 25000,
     "springsSpec": [{"role": "Outer", "wire": 0.2625, "id": 6,
                      "length": 32.25},
                     {"role": "Inner", "wire": 0.1875, "id": 6,
                      "length": 32.25}]},
    {"assembly": "Single", "springs": 9, "doorWeight": 355,
     "doorHeight": "7' 0\"", "doorWidth": "9' 0\"", "hiLift": 0,
     "cycles": 25000,
     "springsSpec": [{"role": "Spring", "wire": 0.2625, "id": 6,
                      "length": 32.25}]},
    {"assembly": "Nonsense", "springs": 2, "doorWeight": 355,
     "doorHeight": "7' 0\"", "doorWidth": "9' 0\"", "hiLift": 0,
     "cycles": 25000,
     "springsSpec": [{"role": "Spring", "wire": 0.2625, "id": 6,
                      "length": 32.25}]},
]


@tagged("post_install", "-at_install")
class TestMatchesTheOriginal(TransactionCase):

    def setUp(self):
        super().setUp()
        self.original = original()

        if not self.original:
            self.skipTest("spring_engineering is not installed here")

    def _renames(self):
        """The generator's own rename table, loaded from the script.

        `tools/` is not a package on the addons path, so it is loaded by file
        path rather than imported.
        """
        spec = importlib.util.spec_from_file_location(
            "aa_build_spring_calculator",
            ROOT / "tools/build_spring_calculator.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return module.RENAMES

    def _quote(self, module, spec):
        """`quote_assembly` reads the rates off `request.env`, so it needs a
        request. The function itself wants nothing else from one."""
        with patch.object(module, "request", SimpleNamespace(env=self.env)):
            return module.quote_assembly(spec)

    def test_every_quote_matches(self):
        """THE ONE THAT MATTERS. Same spec in, same quote out - price,
        description, turns, filler, the lot."""
        for spec in GRID:
            with self.subTest(spec=spec):
                self.assertEqual(
                    self._quote(ours(), spec),
                    self._quote(self.original, spec),
                    "the generated engine no longer agrees with the original -"
                    " run: python3 tools/build_spring_calculator.py")

    def test_the_pricing_constants_match(self):
        """Cone prices, the filler rate and both steel rates. A quote can
        only be right if these are, and they are the figures most likely to
        be edited without a thought for the copy."""
        theirs = importlib.import_module("odoo.addons.spring_engineering.pricing")
        mine = importlib.import_module("odoo.addons.spring_calculator.pricing")

        for name in ("STEEL_PRICE_PER_LB", "STEEL_COST_PER_LB",
                     "FILLER_PRICE_PER_FOOT", "FILLER_SPRING_ID",
                     "CONE_PRICES"):
            self.assertEqual(getattr(mine, name), getattr(theirs, name), name)

    def test_the_assemblies_offered_match(self):
        """Including which are refused - turning Duplex back on in one and
        not the other would sell a spring the shop cannot make."""
        self.assertEqual(ours().ASSEMBLIES, self.original.ASSEMBLIES)
        self.assertEqual(ours().UNBUILDABLE_ASSEMBLIES,
                         self.original.UNBUILDABLE_ASSEMBLIES)

    def test_the_browser_engine_is_the_same_file(self):
        """The sizing maths is 4,449 lines of JavaScript, and none of the
        tests above touch it - they run the PYTHON. So it is compared as
        text, after undoing the renames the generator applied."""
        theirs = (ROOT / "spring_engineering/static/src/js/"
                  "spring_engineering.js").read_text()
        mine = (ROOT / "spring_calculator/static/src/js/"
                "spring_calculator.js").read_text()

        # Drop the generated banner, then put the old names back. The rename
        # table is read out of the generator itself rather than copied here,
        # or this test would need editing every time one is added - and a
        # stale copy of it would pass while the files differed.
        mine = mine.split("\n", 1)[1]

        for old, new in self._renames():
            mine = mine.replace(new, old)

        self.assertEqual(mine, theirs,
                         "the browser engine has drifted - run:"
                         " python3 tools/build_spring_calculator.py")

    def test_the_generated_module_is_current(self):
        """Belt and braces over all of the above: re-run the generator in
        --check mode and let it compare every file it owns, including the
        ones no test above looks at."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/build_spring_calculator.py"),
             "--check"],
            capture_output=True, text=True)

        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)
