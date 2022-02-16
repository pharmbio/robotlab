from setuptools import setup

requirements = '''
    flask
'''

name='imx_pharmbio_automation'

console_scripts = f'''
    pf-moves={name}.pf.gui:main
    pf-flash={name}.pf.flash:main
'''

packages=f'''
    {name}
    {name}.pf
    {name}.utils
    {name}.scheduler
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
