from setuptools import setup

requirements = '''
    flask
    pyserial
    typing_extensions
'''

console_scripts = '''
    labrobots=labrobots:main
'''

name='labrobots'

packages=f'''
    labrobots
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
