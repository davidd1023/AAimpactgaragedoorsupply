def post_init_hook(env):
    """Number every stocked product the moment the module is installed."""
    env['product.product']._aa_assign_all()
