"""WHAT THE STICKER IS PRINTED ON, as a setting rather than as code.

"We don't know what sticker size we are going to use yet" (owner, 2026-10-19).
So the size is a choice in Manufacturing > Settings - the common label stock by
name, or any size at all typed in inches - and the label lays itself out to fit
whatever is chosen. A size nobody has settled on does not belong in a report
template that has to be edited and deployed to change it.

THE SETTING IS THE TRUTH, not the paper format. The format record is written
from the setting (see _aa_sticker_apply_size) and re-written on every module
update, so the owner's choice survives an update instead of being quietly put
back to whatever shipped.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request

# THE LABEL STOCK, by the names it is sold under. Inches, because that is how
# it is sold here - 4 x 6 is the shipping label every thermal printer takes,
# 2 1/4 x 1 1/4 is the small roll.
#
# The key holds the size, so there is no second table to keep in step: "4x3"
# is four inches by three.
STICKER_SIZES = [
    ("4x6", "4 x 6 in (shipping label)"),
    ("4x4", "4 x 4 in"),
    ("4x3", "4 x 3 in"),
    ("4x2", "4 x 2 in"),
    ("3x2", "3 x 2 in"),
    ("2.25x1.25", "2 1/4 x 1 1/4 in (small roll)"),
    ("8.5x11", "8 1/2 x 11 in (plain paper)"),
    ("custom", "Custom size"),
]

DEFAULT_STICKER_SIZE = "4x6"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    aa_sticker_size = fields.Selection(
        STICKER_SIZES, string="Hardware sticker size",
        default=DEFAULT_STICKER_SIZE,
        config_parameter="aa_shop_floor.sticker_size",
        help="What the hardware box's sticker is printed on. The label lays "
             "itself out to fit, so a smaller sticker prints smaller type "
             "rather than running onto a second label.")
    aa_sticker_width_in = fields.Float(
        string="Sticker width (in)", default=4.0,
        config_parameter="aa_shop_floor.sticker_width_in")
    aa_sticker_height_in = fields.Float(
        string="Sticker height (in)", default=6.0,
        config_parameter="aa_shop_floor.sticker_height_in")

    def set_values(self):
        super().set_values()
        # The parameters are saved by now, so the format is written from them
        # rather than from these fields - one path, the same one an update
        # takes.
        self.env["mrp.production"]._aa_sticker_apply_size()


    # --- WHERE THE STICKER'S QR CODE POINTS -----------------------------------
    #
    # THIS IS WHAT THE THREE-DAY 404 WAS. Owner, 2026-10-28, twice over:
    # *"i still get the not found page when scanning the sticker on my
    # phone"* - and the link he finally sent was
    # `https://aaimpactgaragedoorsupply.com/box/132/...`, the APEX domain,
    # which is not Odoo and does not redirect. The same link on
    # `www.aaimpactgaragedoorsupply.com` returns the box page. One missing
    # `www`, printed onto every sticker, invisible because nobody can
    # proof-read a QR code.
    #
    # The host comes from `web.base.url`, which lives in Settings >
    # Technical > System Parameters - a screen nobody should have to visit to
    # make a sticker work, and one where a typo is another week of this. So
    # it is HERE, with a button that reads the host out of the address bar
    # rather than asking anybody to type it.

    aa_sticker_link_host = fields.Char(
        string="Sticker links point at",
        compute="_compute_aa_sticker_link_host")
    aa_sticker_link_here = fields.Char(
        string="This site", compute="_compute_aa_sticker_link_host")
    aa_sticker_link_frozen = fields.Boolean(
        compute="_compute_aa_sticker_link_host")
    aa_sticker_link_wrong = fields.Boolean(
        compute="_compute_aa_sticker_link_host")

    @api.depends_context("uid")
    def _compute_aa_sticker_link_host(self):
        params = self.env["ir.config_parameter"].sudo()
        base = (params.get_param("web.base.url") or "").rstrip("/")
        frozen = params.get_param("web.base.url.freeze")
        here = self._aa_this_site()

        for settings in self:
            settings.aa_sticker_link_host = base or _("not set")
            settings.aa_sticker_link_here = here
            settings.aa_sticker_link_frozen = bool(
                frozen and frozen not in ("0", "False", "false"))
            # ONLY WHEN BOTH ARE KNOWN AND THEY DISAGREE. Not knowing is not
            # the same as being wrong, and a settings page that cries wolf
            # over a shell session is a settings page nobody believes.
            settings.aa_sticker_link_wrong = bool(here and base and here != base)

    def _aa_this_site(self):
        """The host this page is being served on, straight off the request.

        READ, NEVER TYPED. The whole fault was a host somebody had to know -
        and the one in the address bar is the one that works, by definition,
        because the person is looking at Odoo through it.
        """
        if not request:
            return ""

        return (request.httprequest.host_url or "").rstrip("/")

    def action_aa_sticker_use_this_site(self):
        """Point sticker links at the site this page came in on, and FREEZE it.

        THE FREEZE IS HALF THE FIX. Without `web.base.url.freeze`, Odoo
        rewrites the host to whichever one an administrator last signed in
        from - so this comes back the next time anybody signs in on a bare
        domain, an odoo.sh build URL or an IP, silently, and nobody finds out
        until a phone is held up to a box.
        """
        here = self._aa_this_site()

        if not here:
            raise UserError(_(
                "This has to be done from a browser - there is no address to"
                " read. Set web.base.url by hand in Settings > Technical >"
                " System Parameters."))

        params = self.env["ir.config_parameter"].sudo()
        params.set_param("web.base.url", here)
        params.set_param("web.base.url.freeze", "True")

        return {"type": "ir.actions.client", "tag": "reload"}
