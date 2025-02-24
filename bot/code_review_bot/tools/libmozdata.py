from importlib.metadata import version

import structlog
from libmozdata.config import Config, set_config

logger = structlog.get_logger(__name__)


class LocalConfig(Config):
    """
    Provide required configuration for libmozdata
    using in-memory class instead of an INI file
    """

    def __init__(self, name, version):
        self.user_agent = f"{name}/{version}"
        logger.debug(f"User agent is {self.user_agent}")

    def get(self, section, option, default=None, **kwargs):
        if section == "User-Agent" and option == "name":
            return self.user_agent

        return default


def setup(package_name):
    # Get version for main package
    package_version = version(package_name)

    # Provide to custom libzmodata configuration
    set_config(LocalConfig(package_name, package_version))
