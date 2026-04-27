from setuptools import setup
from mypyc.build import mypycify

setup(
    ext_modules=mypycify([
        "code_normalizer_pro/code_normalizer_pro.py",
    ]),
)