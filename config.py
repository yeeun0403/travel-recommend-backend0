import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', '3Ud9hD29Xd2eB3nF03qYn76V')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', '23h3uinfF38g02873b5Og')
