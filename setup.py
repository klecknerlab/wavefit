from setuptools import setup

setup(
    name='wavefit',
    version='0.1',
    description='Python-based software to find harmonic amplitudes and phases of signals relative to a reference.',
    url='https://github.com/klecknerlab/wavefit',
    author='Dustin Kleckner',
    author_email='dkleckner@ucmerced.edu',
    license='Apache 2.0 (http://www.apache.org/licenses/LICENSE-2.0)',
    packages=['wavefit'],
    install_requires=[ #Many of the packages are not in PyPi, so assume the user knows how to isntall them!
        # 'numpy',
        # 'PyQt5',
    ],
    # scripts=['bin/muvi_convert'],
    entry_points={
        'gui_scripts': ['qtwavefit=wavefit.qt:wavefit_qt_app']
    },
    zip_safe=False
)
