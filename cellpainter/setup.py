from setuptools import setup

requirements = '''
    pbutils
    viable
    z3-solver
    labrobots
'''

console_scripts = '''
    cellpainter=cellpainter.cli:main
    cellpainter-gui=cellpainter.main_gui:main
    cellpainter-moves=cellpainter.moves_gui:main
'''

name='cellpainter'

packages=f'''
    {name}
'''

setup(
    name=name,
    packages=packages.split(),
    version='0.1',
    description='Cell painting using the robot arm',
    url='https://github.com/pharmbio/robotlab',
    author_email='dan.rosen@farmbio.uu.se',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
