from .utils import *

module_name = "utils." + config.get("lang").get("prefix") + ".text"
import_all_from_module(module_name)
