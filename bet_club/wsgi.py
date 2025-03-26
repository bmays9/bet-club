"""
WSGI config for bet_club project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

try:
    import env  # noqa
except ImportError:
    print("Warning: env.py not found!")

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bet_club.settings')

application = get_wsgi_application()
