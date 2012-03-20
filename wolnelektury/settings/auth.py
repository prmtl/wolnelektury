AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
EMAIL_CONFIRMATION_DAYS = 2
LOGIN_URL = '/uzytkownik/login/'

LOGIN_REDIRECT_URL = '/'
