# -*- coding: utf-8 -*-
# This file is part of Wolnelektury, licensed under GNU Affero GPLv3 or later.
# Copyright © Fundacja Nowoczesna Polska. See NOTICE for more information.
#
from django.contrib import admin

from suggest.models import Suggestion

class SuggestionAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'contact', 'user', 'description')

admin.site.register(Suggestion, SuggestionAdmin)
