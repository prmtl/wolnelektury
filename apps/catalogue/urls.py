# -*- coding: utf-8 -*-
# This file is part of Wolnelektury, licensed under GNU Affero GPLv3 or later.
# Copyright © Fundacja Nowoczesna Polska. See NOTICE for more information.
#
from django.conf.urls.defaults import *
from catalogue.feeds import AudiobookFeed


urlpatterns = patterns('catalogue.views',
    url(r'^$', 'catalogue', name='catalogue'),
    url(r'^polki/(?P<shelf>[a-zA-Z0-9-]+)/formaty/$', 'shelf_book_formats', name='shelf_book_formats'),
    url(r'^polki/(?P<shelf>[a-zA-Z0-9-]+)/(?P<book>[a-zA-Z0-9-0-]+)/usun$', 'remove_from_shelf', name='remove_from_shelf'),
    url(r'^polki/$', 'user_shelves', name='user_shelves'),
    url(r'^polki/(?P<slug>[a-zA-Z0-9-]+)/usun/$', 'delete_shelf', name='delete_shelf'),
    url(r'^polki/(?P<slug>[a-zA-Z0-9-]+)\.zip$', 'download_shelf', name='download_shelf'),
    url(r'^lektury/', 'book_list', name='book_list'),
    url(r'^audiobooki/$', 'audiobook_list', name='audiobook_list'),
    url(r'^daisy/$', 'daisy_list', name='daisy_list'),
    url(r'^lektura/(?P<slug>[a-zA-Z0-9-]+)/polki/', 'book_sets', name='book_shelves'),
    url(r'^polki/nowa/$', 'new_set', name='new_set'),
    url(r'^tags/$', 'tags_starting_with', name='hint'),
    url(r'^jtags/$', 'json_tags_starting_with', name='jhint'),
    url(r'^szukaj/$', 'search', name='search'),

    # zip
    #url(r'^zip/pdf\.zip$', 'download_zip', {'format': 'pdf', 'slug': None}, 'download_zip_pdf'),
    #url(r'^zip/epub\.zip$', 'download_zip', {'format': 'epub', 'slug': None}, 'download_zip_epub'),
    #url(r'^zip/mobi\.zip$', 'download_zip', {'format': 'mobi', 'slug': None}, 'download_zip_mobi'),
    #url(r'^zip/audiobook/(?P<slug>[a-zA-Z0-9-]+)\.zip', 'download_zip', {'format': 'audiobook'}, 'download_zip_audiobook'),

    # tools
    url(r'^zegar/$', 'clock', name='clock'),

    # Public interface. Do not change this URLs.
    url(r'^lektura/(?P<slug>[a-zA-Z0-9-]+)\.html$', 'book_text', name='book_text'),
    url(r'^lektura/(?P<slug>[a-zA-Z0-9-]+)/$', 'book_detail', name='book_detail'),
    url(r'^lektura/(?P<book_slug>[a-zA-Z0-9-]+)/motyw/(?P<theme_slug>[a-zA-Z0-9-]+)/$',
        'book_fragments', name='book_fragments'),

    url(r'^(?P<tags>[a-zA-Z0-9-/]*)/$', 'tagged_object_list', name='tagged_object_list'),

    url(r'^audiobooki/(?P<type>mp3|ogg|daisy|all).xml$', AudiobookFeed(), name='audiobook_feed'),
)

