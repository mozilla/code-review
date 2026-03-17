from importlib import import_module


def register(graph_config):
    _import_modules(["parameters"])


def _import_modules(modules):
    for module in modules:
        import_module(f".{module}", package=__name__)
