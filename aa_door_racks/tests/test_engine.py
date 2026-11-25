from odoo.tests import BaseCase

from ..models import engine

RULES = engine.Rules()
AD = [0, 74.5, 134.5, 209]
E = [0, 74, 148]


def side(key="A", arms=AD, fallback=True):
    return engine.SideSpec(key=key, arms=list(arms), overhang=24, allow_fallback=fallback,
                           levels={key + "1": 39, key + "2": 36, key + "5": 0},
                           level_numbers={key + "1": 1, key + "2": 2, key + "5": 5})


class TestEngine(BaseCase):

    def test_height(self):
        self.assertEqual(engine.bundle_height([4], RULES), 13)
        self.assertEqual(engine.bundle_height([4, 4], RULES), 27.5)

    def test_support_rules(self):
        a, e = side(), side("E", E, False)
        self.assertEqual(engine.support_groups(a, 96, RULES), [(0, 1), (1, 2), (2, 3)])
        # 11': no three arms in reach on A-D, so one 74.5" unit
        self.assertEqual(engine.support_groups(a, 132, RULES), [(0, 1), (2, 3)])
        self.assertEqual(engine.support_groups(a, 144, RULES), [(0, 2), (1, 3)])
        self.assertEqual(engine.support_groups(e, 132, RULES), [])
        self.assertEqual(engine.support_groups(e, 192, RULES), [(0, 2)])
        # past the 24" overhang it does not fit at all
        self.assertIsNone(engine.start_range(e, 0, 2, 200))

    def test_two_small_side_by_side_and_not_on_the_middle(self):
        a = side()
        c = engine.candidates([a], [], 96, 12, RULES)
        best = c[0]
        self.assertNotEqual((best.arm_from, best.arm_to), (1, 2), "the middle pair strands both outer arms")
        placed = [engine.Placed(1, "A", best.level, best.depth, best.arm_from, best.arm_to,
                                best.start, 96, 12)]
        c2 = engine.candidates([a], placed, 96, 12, RULES)
        self.assertEqual((c2[0].level, c2[0].depth), (best.level, best.depth), "fills the same row first")
        self.assertTrue(c2[0].stacked or {c2[0].arm_from, c2[0].arm_to}.isdisjoint({best.arm_from, best.arm_to}))

    def test_e_middle_arm_is_never_shared(self):
        e = side("E", E, False)
        p = [engine.Placed(1, "E", "E1", "back", 0, 1, 0, 96, 12)]
        for c in engine.candidates([e], p, 96, 12, RULES):
            if (c.level, c.depth) == ("E1", "back"):
                self.assertEqual((c.arm_from, c.arm_to), (0, 1))
                self.assertTrue(c.stacked)

    def test_two_elevens_do_not_fit_side_by_side(self):
        a = side()
        p = [engine.Placed(1, "A", "A1", "back", 0, 1, -24, 132, 12)]
        for c in engine.candidates([a], p, 132, 12, RULES):
            if (c.level, c.depth) == ("A1", "back"):
                self.assertTrue(c.stacked)

    def test_height_limit_and_top_level(self):
        a = side()
        tall = engine.candidates([a], [], 96, 45, RULES)
        self.assertTrue(tall)
        self.assertTrue(all(c.level == "A5" for c in tall))

    def test_back_only_behind_an_empty_front(self):
        a = side()
        p = [engine.Placed(1, "A", "A1", "front", 0, 1, -10, 96, 12)]
        for c in engine.candidates([a], p, 96, 12, RULES):
            if c.level == "A1" and c.depth == "back":
                self.assertNotIn(0, range(c.arm_from, c.arm_to + 1))

    def test_big_door_prefers_e(self):
        a, e = side(), side("E", E, False)
        best = engine.candidates([a, e], [], 192, 12, RULES)[0]
        self.assertEqual(best.side, "E")
