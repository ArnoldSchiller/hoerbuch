from setuptools import setup, find_packages

setup(
    name="hoerbuch",
    version="1.0.0",
    description="Convert text documents to audiobooks using Piper TTS",
    author="Arnold Schiller",
    packages=find_packages(),
    py_modules=["hoerbuch"],
    entry_points={
        'console_scripts': [
            'hoerbuch=hoerbuch:main',
        ],
    },
    install_requires=[
        'piper-tts',
        'soundfile',
        'mutagen',
        'numpy',
        'lxml',
        'python-docx',
        'ebooklib',
        'odfpy',
    ],
    python_requires='>=3.6',
    include_package_data=True,
    data_files=[
        ('share/locale/de/LC_MESSAGES', ['locales/de/LC_MESSAGES/messages.mo']),
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GPL 3.0 License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.13',
    ],
)
