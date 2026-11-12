"""THE GAP NO MODEL TEST CAN REACH: does the JavaScript get to the browser?

The sizing maths is 4,449 lines of JavaScript, and the carve renamed two
things inside it - the Owl template (`spring_calculator.Calculator`) and the
public component (`spring_calculator.calculator`). Get either wrong and the
page serves a perfect HTTP 200 carrying an EMPTY BOX: the route works, the
template renders, the component never mounts, and every test in
`test_stands_alone` still passes.

FOUR NAMES HAVE TO AGREE for the calculator to appear at all:

    the page            <owl-component name="spring_calculator.calculator"/>
    the registry        .add("spring_calculator.calculator", ...)
    the component       static template = "spring_calculator.Calculator"
    the template        <t t-name="spring_calculator.Calculator">

`TestTheAssetChain` checks all four, and checks them in the bundle the server
actually SERVES rather than in the files on disk - an asset that never made it
into the bundle is the same as one that does not exist.

`TestInABrowser` is the stronger proof and needs Chrome. It SKIPS where the
container cannot start one, which is this build: the shared host runs at load
20+ and Chrome dies with "can't start new thread". It is kept because it runs
on the second project, and because a skip that says why is worth more than a
test quietly deleted.

Both need the module INSTALLED, and it deliberately is not here - it would
take /spring-calculator off the original (see the README):

    odoo-bin -i spring_calculator --stop-after-init --no-http
    odoo-bin --test-tags /spring_calculator --stop-after-init
    # then uninstall it again
"""

import re

from odoo.tests.common import HttpCase, tagged

PAGE = "/spring-calculator"
COMPONENT = "spring_calculator.calculator"
TEMPLATE = "spring_calculator.Calculator"


@tagged("post_install", "-at_install")
class TestTheAssetChain(HttpCase):

    def _page(self):
        answer = self.url_open(PAGE)

        self.assertEqual(answer.status_code, 200)

        return answer.text

    def test_the_page_mounts_the_component(self):
        self.assertIn(f'name="{COMPONENT}"', self._page())

    def test_the_component_and_its_template_reach_the_browser(self):
        """THE ONE THAT WOULD CATCH A BOTCHED RENAME. Fetched from the
        served bundle, not read off disk."""
        page = self._page()
        bundles = [b for b in re.findall(r'/web/assets/[^"\']+\.js', page)]

        self.assertTrue(bundles, "the page loaded no javascript at all")

        served = ""
        for bundle in sorted(set(bundles)):
            served += self.url_open(bundle).text

        self.assertIn(f'"{COMPONENT}"', served,
                      "the calculator is not registered in any bundle the "
                      "page loads - it would mount nothing")
        self.assertIn(TEMPLATE, served,
                      "the Owl template is not in any bundle the page loads "
                      "- the component would mount and render nothing")

    def test_it_is_not_the_originals_component(self):
        """If the carved page mounted `spring_engineering.calculator` it
        would work perfectly HERE, where the original is installed, and
        render nothing at all on the second project."""
        self.assertNotIn('name="spring_engineering.calculator"', self._page())


@tagged("post_install", "-at_install")
class TestInABrowser(HttpCase):

    def test_the_calculator_mounts_and_computes(self):
        code = """
            (async () => {
                const deadline = Date.now() + 30000;

                const wait = async (selector, what) => {
                    while (Date.now() < deadline) {
                        if (document.querySelector(selector)) {
                            return;
                        }
                        await new Promise((r) => setTimeout(r, 200));
                    }
                    throw new Error(what + " (" + selector + ")");
                };

                await wait(".spring-engineering",
                           "the calculator never mounted - the Owl template "
                           + "or the public component name is wrong");

                // NOTHING IS SHOWN UNTIL IT HAS WHAT IT NEEDS - a drum and a
                // weight above zero (see `get resultsVisible`). So the form
                // is driven, which is the point: it makes this a test of the
                // ENGINE rather than of the shell it sits in.
                const set = (el, value, proto) => {
                    const setter = Object.getOwnPropertyDescriptor(
                        proto.prototype, "value").set;
                    setter.call(el, value);
                    el.dispatchEvent(new Event("input", { bubbles: true }));
                    el.dispatchEvent(new Event("change", { bubbles: true }));
                };

                const rows = [...document.querySelectorAll(".se-row")];
                const weightRow = rows.find((r) =>
                    /Weight/.test((r.querySelector("span") || {}).textContent || ""));

                if (!weightRow) {
                    throw new Error("no Weight row on the form");
                }

                set(weightRow.querySelector("input"), "355", HTMLInputElement);

                const drum = [...document.querySelectorAll("select.se-select")]
                    .find((s) => /Select a Drum/.test(s.textContent));

                if (!drum) {
                    throw new Error("no drum selector on the form");
                }

                const choice = [...drum.options].find((o) => o.value);
                set(drum, choice.value, HTMLSelectElement);

                // It got as far as pricing something, so the engine RAN
                // rather than merely rendering its chrome.
                await wait(".se-rowR-total",
                           "the calculator mounted but produced no figure - "
                           + "the engine did not run");

                const total = document.querySelector(".se-rowR-total")
                    .textContent;

                if (!/[0-9]/.test(total)) {
                    throw new Error("the total carries no figure: " + total);
                }

                console.log("test successful");
            })();
        """

        # ON 2026-11-02 THIS RAN ONCE AND GOT PAST THE FIRST WAIT: the
        # calculator MOUNTED in a real browser, which is the thing the rename
        # put at risk. It then failed the second wait because the original
        # version of this test assumed the results were on screen at load -
        # they are not, `resultsVisible` wants a drum and a weight, which is
        # why the form is now driven above. Chrome would not start again
        # afterwards, so the driven version is unverified HERE and wants a
        # run on the second project.
        try:
            self.browser_js(PAGE, code, login=None)
        except RuntimeError as error:
            if "can't start new thread" in str(error):
                self.skipTest(
                    "no browser here: the container cannot start Chrome under"
                    " this host's load (seen at 21). The asset chain is"
                    " checked by TestTheAssetChain instead; run this on the"
                    " second project for the full proof.")
            raise
