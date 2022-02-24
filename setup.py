from setuptools import setup

requirements = '''
    flask
'''

name='imager'

console_scripts = f'''
    pf-moves={name}.moves_gui:main
    pf-flash={name}.flash:main
    imager={name}.cli:main
'''

packages=f'''
    {name}
    {name}.utils
'''

setup(
    name=name,
    packages=packages.split(),
    version='0.1',
    description='IMX imaging using the PreciseFlex robot arm and LiCONiC fridge',
    url='https://github.com/pharmbio/robot-imager',
    author='Dan Rosén',
    author_email='dan.rosen@farmbio.uu.se',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
