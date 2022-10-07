from setuptools import setup

requirements = '''
    flask>=2.0.2
    itsdangerous>=2.0
'''

name='viable'

console_scripts = f'''
'''

packages=f'''
    {name}
'''

setup(
    name=name,
    packages=packages.split(),
    version='0.1',
    description='A viable alternative to frontend programming for python',
    url='https://github.com/pharmbio/robotlab',
    author='Dan Rosén',
    author_email='danr42@gmail.com',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
