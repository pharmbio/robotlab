from setuptools import setup

# install tesseract windows binaries from: https://github.com/UB-Mannheim/tesseract/wiki

requirements = '''
    pillow
    pytesseract
    pywin32
    numpy
    scipy
'''

console_scripts = '''
    nikon_screen_scraper=nikon_screen_scraper:main
'''

setup(
    name='nikon_screen_scaper',
    py_modules=['nikon_screen_scaper'],
    version='0.1',
    description='Nikon screen scaper: screenshot the nikon gui and use OCR to get the acquisition time remaining information',
    url='https://github.com/danr/nikon_screen_scaper',
    author='Dan Rosén',
    author_email='danr42@gmail.com',
    python_requires='>=3.10',
    license='MIT',
    install_requires=requirements.split(),
    entry_points={'console_scripts': console_scripts.split()}
)
