from setuptools import setup

requirements = '''
    flask
'''

console_scripts = '''
    labrobots-server=labrobots_server.main:main
    labrobots-example-repl=labrobots_server.main:example_repl
    incubator-repl=incubator_repl.incubator:main
'''

name='labrobots'

packages=f'''
    labrobots_server
    incubator_repl
'''

setup(
    name=name,
    packages=packages.split(),
    version='0.1',
    description='Web server to our LiCONiC incubator and BioTek washer and dispenser.',
    url='https://github.com/pharmbio/robotlab-labrobots',
    author='Dan Rosén, Anders Larsson',
    author_email='dan.rosen@farmbio.uu.se, anders.larsson@nbis.se',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
