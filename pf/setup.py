from setuptools import setup

requirements = '''
    flask
'''

console_scripts = '''
    pf-moves=pf.gui:main
    pf-flash=pf.flash:main
'''

name='pf'

packages=f'''
    {name}
    {name}.utils
'''

setup(
    name=name,
    packages=packages.split(),
    version='0.1',
    description='Move the PreciseFlex robotarm to serve the IMX microscope',
    url='https://github.com/pharmbio/imx-pharmbio-automation',
    author='Dan Rosén',
    author_email='dan.rosen@farmbio.uu.se',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
