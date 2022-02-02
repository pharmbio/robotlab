from setuptools import setup

requirements = '''
    flask
    pyserial
'''

console_scripts = '''
    imx-server=imx_server.main:main
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
