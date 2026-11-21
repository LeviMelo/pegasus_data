"""Modelled products built on the data: the population account, its tensor, backcast and forecast, the race
confusion models, registration completeness and the SUS-dependent population. Nothing below this package imports it:
a product is built by the function its entry in ``curation/products.yml`` names (``pegasus-data model-build``) and
read back through ``modelled.read_modelled``. The fitting stack (JAX, NumPyro) is the ``modelled`` extra.
"""
