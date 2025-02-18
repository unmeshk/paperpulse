from setuptools import setup, find_packages

setup(
    name="arxivsum",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        'openai',
        'python-dotenv',
        'pdfplumber',
        'PyMuPDF',
        'Pillow',
        'Flask',
        'urllib3',
        'requests'
    ],
    entry_points={
        'console_scripts': [
            'arxivsum=api.main:main',
        ],
    },
)