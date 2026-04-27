from setuptools import setup

# mypyc produces a compiled C-extension wheel for performance.
# On machines where mypyc or the C compiler is unavailable (AppLocker
# policies, minimal CI images, user installs), fall back to a pure-Python
# wheel automatically. The compiled wheel is built by cibuildwheel in CI.
try:
    from mypyc.build import mypycify
    ext_modules = mypycify(["code_normalizer_pro/code_normalizer_pro.py"])
except Exception:
    ext_modules = []

setup(ext_modules=ext_modules)