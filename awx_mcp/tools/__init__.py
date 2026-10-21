# SPDX-License-Identifier: Apache-2.0
"""Import tool modules to collect specs. Exposure is explicit at startup.

Sorted discovery preserves the existing alphabetical module order and makes
new modules discoverable without an easily forgotten manual import entry.
"""

from importlib import import_module
from pkgutil import iter_modules

for _module in sorted(iter_modules(__path__), key=lambda entry: entry.name):
    if not _module.name.startswith("_"):
        globals()[_module.name] = import_module(f"{__name__}.{_module.name}")
