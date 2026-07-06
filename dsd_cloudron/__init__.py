from .deploy import dsd_get_plugin_config
from .deploy import dsd_deploy

# Re-exported so django-simple-deploy core discovers the hook implementations on
# the package. Naming them in __all__ marks the re-export as intentional.
__all__ = ["dsd_get_plugin_config", "dsd_deploy"]
