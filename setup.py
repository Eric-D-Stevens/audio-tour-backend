from setuptools import setup, find_packages

setup(
    name="tensortours",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "boto3>=1.28.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "tenacity>=8.2.3",
        "openai>=1.3.0",
        "pydantic>=2.0.0",
        "python-dateutil>=2.8.2",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-mock>=3.10.0",
            "moto>=4.0.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
        ]
    },
    python_requires=">=3.12",
)
