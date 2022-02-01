from setuptools import setup

requirements = '''
    z3-solver
    flask
    sorcery
'''

console_scripts = '''
    cellpainter=cellpainter.cli:main
    cellpainter-gui=cellpainter.main:main
'''

name='cellpainter'

packages=f'''
    {name}
    {name}.utils
'''

setup(
    name=name,
    packages=packages.split(),
    version='0.1',
    description='Cell painting using the robot arm',
    url='https://github.com/pharmbio/robot-remote-control',
    author='Dan Rosén',
    author_email='dan.rosen@farmbio.uu.se',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
