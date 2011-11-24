# -*- coding: utf-8 -*-
# This file is part of Wolnelektury, licensed under GNU Affero GPLv3 or later.
# Copyright © Fundacja Nowoczesna Polska. See NOTICE for more information.
#
from django.conf.urls.defaults import *


urlpatterns = patterns('social.views',
    url(r'^podkresl/(?P<slug>[a-zA-Z0-9-]+)/$', 'underline', name='social_underline'),
    url(r'^skomentuj/(?P<slug>[a-zA-Z0-9-]+)/$', 'comment', name='social_comment_underline'),
)

