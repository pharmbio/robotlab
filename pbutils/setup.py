from setuptools import setup

requirements = '''
    apsw>=3.39.3
    executing
'''

console_scripts = '''
    pbutils-check=pbutils.check:main
'''

name='pbutils'

packages=f'''
    {name}
'''

setup(
    name=name,
    packages=packages.split(),
    version='0.1',
    description='Shared utilities',
    url='https://github.com/pharmbio/robotlab',
    author='Dan Rosén',
    author_email='dan.rosen@farmbio.uu.se',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
