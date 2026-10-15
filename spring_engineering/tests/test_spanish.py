import re

from odoo.tests.common import HttpCase, TransactionCase, tagged
from odoo.tools.misc import file_path
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestTheCalculatorSpeaksSpanish(TransactionCase):
    """Switching the website to Spanish has to take the calculator with it.

    The terms are read off the .po FILE, not out of the database, which is how
    Odoo serves them too - so none of this needs the language installed and
    none of it can be fooled by a stale database.
    """

    LANG = "es_ES"
    MODULE = "spring_engineering"

    def _web(self):
        """What the browser is sent: the terms marked odoo-javascript."""
        web = code_translations.get_web_translations(self.MODULE, self.LANG)

        return {m["id"]: m["string"] for m in web["messages"]}

    def _po(self):
        path = file_path(f"{self.MODULE}/i18n/es.po")

        with open(path, encoding="utf-8") as f:
            return f.read()

    def _entries(self):
        """Every msgid/msgstr pair in the file, as plain strings.

        A .po WRAPS. Anything much over seventy characters is written as a run
        of quoted lines that the reader joins, so a long warning is simply not
        in the file as one piece of text - which is what this used to look for,
        and why it reported eight perfectly good translations as missing.
        """
        pairs = re.findall(
            r'^msgid ((?:"(?:[^"\\]|\\.)*"\s*)+)msgstr ((?:"(?:[^"\\]|\\.)*"\s*)+)',
            self._po(), re.M)
        out = []

        for raw_id, raw_str in pairs:
            join = lambda raw: "".join(
                re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
            ).replace('\\"', '"').replace("\\\\", "\\")
            out.append((join(raw_id), join(raw_str)))

        return out

    # --- the labels and the warnings -----------------------------------------

    def test_the_frame_of_the_calculator_is_translated(self):
        web = self._web()

        for source, spanish in (
            ("Assembly", "Conjunto"),
            ("Springs", "Resortes"),
            ("Drum", "Tambor"),
            ("Wire Size", "Calibre del alambre"),
            ("Turns", "Vueltas"),
            ("Add to Cart", "Agregar al carrito"),
            ("Select a Drum", "Seleccione un tambor"),
        ):
            self.assertEqual(web.get(source), spanish, source)

    def test_the_warnings_are_translated(self):
        """A WARNING IS THE POINT OF THE TOOL. A Spanish-speaking fitter who
        cannot read the one that says the wire is over the limit is worse off
        than one who sees no calculator at all."""
        web = self._web()

        for source in (
            "Wire size exceeds %s maximum for this I.D.",
            "Wire size is less than the minimum of %s for this I.D.",
            "This wire size computes to %s. Low Cycle Life",
            "Use extreme caution when designing springs for use with this drum.",
            'The current height entered is greater than this drum will allow!'
            ' The maximum height of this drum is %s".',
            "The current weight entered is heavier than this drum will allow!"
            " The maximum weight of this drum is %s lb.",
        ):
            self.assertTrue(web.get(source), f"untranslated: {source}")
            self.assertNotEqual(web[source], source, source)

    def test_the_server_side_refusals_are_translated(self):
        python = code_translations.get_python_translations(self.MODULE, self.LANG)
        source = ("Orders start at %(minimum)s. Your cart comes to %(total)s,"
                  " so please add %(short)s more before checking out.")

        self.assertTrue(python.get(source), "the minimum-order refusal")

    # --- what must NOT be translated -----------------------------------------

    def test_part_numbers_are_left_alone(self):
        """A DRUM NAME IS ALSO A VALUE, not just a label.

        The component matches state.drum against its own tables, and a fitter
        orders a CANIMEX/TF D400-96 by that name in any language. The same
        goes for the spring sizes and for TIPPT and LHR.
        """
        web = self._web()

        for source in ("CANIMEX/TF D400-96", "CANIMEX/TF D525-216",
                       "RAYNOR 1022 & 23", "APCO 850-11", "TIPPT", "LHR",
                       '3 3/4" inside 6"'):
            self.assertIsNone(
                web.get(source),
                f"{source} was translated - it is a catalogue identifier")

    # --- the file itself has to stay sound -----------------------------------

    def test_no_translation_drops_a_placeholder(self):
        """%s AND %(name)s ARE NOT DECORATION. A translation that loses one
        prints the wrong number, or none; one that gains one raises. Either
        way the customer is told something untrue by a tool whose whole job is
        to be exact."""
        holder = re.compile(r"%\([a-z_]+\)s|%s")
        checked = 0

        for msgid, msgstr in self._entries():
            if not msgid or not msgstr:
                continue

            checked += 1
            self.assertEqual(
                sorted(holder.findall(msgid)), sorted(holder.findall(msgstr)),
                f"placeholders differ:\n  {msgid}\n  {msgstr}")

        self.assertGreater(checked, 50, "the file looks empty")

    def test_every_string_the_calculator_can_show_is_in_the_file(self):
        """A TRIPWIRE FOR THE NEXT STRING SOMEBODY ADDS.

        A new _t() in the component is invisible until somebody exports the
        terms again - it simply shows in English on a Spanish page, which is
        exactly the kind of thing nobody notices for months. This fails
        instead, and the fix is to re-export and translate the new line.
        """
        path = file_path(f"{self.MODULE}/static/src/js/spring_engineering.js")

        with open(path, encoding="utf-8") as f:
            source = f.read()

        # The first argument of each _t(...), including the ones written as
        # several string literals joined with +.
        calls = re.findall(
            r'_t\(\s*((?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')'
            r'(?:\s*\+\s*(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'))*)',
            source)
        known = {msgid for msgid, _ in self._entries()}
        missing = []

        for call in calls:
            # Join the literals the way JavaScript would, then quote them the
            # way a .po file does.
            parts = re.findall(
                r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'', call)
            msgid = "".join(double or single for double, single in parts)

            if not msgid:
                continue

            if msgid not in known:
                missing.append(msgid)

        self.assertFalse(
            missing,
            "these are shown by the calculator but are not in i18n/es.po - "
            "re-export the terms and translate them:\n  "
            + "\n  ".join(missing))


@tagged("post_install", "-at_install")
class TestTheShopIsSentTheSpanish(HttpCase):
    """What /website/translations actually puts on the wire.

    Everything else in here reads files and registries. This asks the running
    website the same question the browser asks it, which is the only check
    that would have caught the module being absent from the frontend list.
    """

    def test_the_calculators_terms_are_in_the_frontend_payload(self):
        self.env["res.lang"]._activate_lang("es_ES")

        body = self.url_open(
            "/website/translations?lang=es_ES", timeout=60).text

        self.assertIn("Conjunto", body, "the shop is not sent 'Assembly'")
        self.assertIn("Calibre del alambre", body, "nor 'Wire Size'")
        self.assertIn("Tambor", body, "nor 'Drum'")
        # The one the global pool gets wrong when this module is missing:
        # website's own file translates "Single" as the marital status.
        self.assertIn("Simple", body, "'Single' is not coming from this module")
