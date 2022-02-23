from setuptools import setup

requirements = '''
    flask
    pyserial
'''

console_scripts = '''
    labrobots-server=labrobots_server.main:main
    labrobots-example-repl=labrobots_server.main:example_repl
    labrobots-dir-list-repl=labrobots_server.dir_list_repl:main
    incubator-repl=incubator_repl.main:main
    barcode-repl=barcode_repl.main:main
    imx-repl=imx_repl.main:main
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
    description='Web server to our LiCONiC incubator&fridge, BioTek washer&dispenser, IMX microscope and Honeywell barcode scanner.',
    url='https://github.com/pharmbio/robotlab-labrobots',
    author='Dan Rosén, Anders Larsson',
    author_email='dan.rosen@farmbio.uu.se, anders.larsson@nbis.se',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)


from setuptools import setup

requirements = '''
    flask
    pyserial
'''

console_scripts = '''
'''

name='imx-server'

packages=f'''
    imx_server
'''

setup(
    name=name,
    packages=packages.split(),
    version='0.1',
    description='Expose the IMX microscope External Control Protocol COM port using flask',
    url='https://github.com/pharmbio/imx-pharmbio-automation',
    author='Dan Rosén',
    author_email='dan.rosen@farmbio.uu.se',
    python_requires='>=3.8',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
