import os
from setuptools import setup

# mypyc produces a compiled C-extension wheel for performance.
# It is only attempted when CNP_COMPILE=1 is set (e.g. in cibuildwheel CI).
# Regular `pip install` and `python -m build` always get the pure-Python wheel.
ext_modules = []
if os.environ.get("CNP_COMPILE") == "1":
    try:
        from mypyc.build import mypycify
        ext_modules = mypycify(["code_normalizer_pro/code_normalizer_pro.py"])
    except Exception:
        pass  # compiler or mypyc unavailable — fall back to pure Python

setup(ext_modules=ext_modules)
