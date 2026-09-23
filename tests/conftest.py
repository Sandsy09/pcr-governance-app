import os

import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "pcr_governance_app.config.settings",
)
django.setup()
