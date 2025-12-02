from setuptools import setup, find_packages

setup(
    name="telegram-drive-bot",
    version="1.0.0",
    packages=find_packages(),
    python_requires=">=3.11,<3.13",
    install_requires=[
        "python-telegram-bot==20.7",
        "google-api-python-client==2.108.0",
        "google-auth-httplib2==0.2.0",
        "google-auth-oauthlib==1.2.0",
        "APScheduler==3.10.4",
        "python-dotenv==1.0.0",
        "psycopg2-binary==2.9.9",
    ],
)
