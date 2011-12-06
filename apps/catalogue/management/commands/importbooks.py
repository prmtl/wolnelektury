# -*- coding: utf-8 -*-
# This file is part of Wolnelektury, licensed under GNU Affero GPLv3 or later.
# Copyright © Fundacja Nowoczesna Polska. See NOTICE for more information.
#
import os
import sys
import time
from optparse import make_option

from django.core.management.base import BaseCommand
from django.core.management.color import color_style
from django.core.files import File

from catalogue.models import Book


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('-q', '--quiet', action='store_false', dest='verbose', default=True,
            help='Verbosity level; 0=minimal output, 1=normal output, 2=all output'),
        make_option('-f', '--force', action='store_true', dest='force', default=False,
            help='Print status messages to stdout'),
        make_option('-E', '--no-build-epub', action='store_false', dest='build_epub', default=True,
            help='Don\'t build EPUB file'),
        make_option('-M', '--no-build-mobi', action='store_false', dest='build_mobi', default=True,
            help='Don\'t build MOBI file'),
        make_option('-T', '--no-build-txt', action='store_false', dest='build_txt', default=True,
            help='Don\'t build TXT file'),
        make_option('-P', '--no-build-pdf', action='store_false', dest='build_pdf', default=True,
            help='Don\'t build PDF file'),
        make_option('-w', '--wait-until', dest='wait_until', metavar='TIME',
            help='Wait until specified time (Y-M-D h:m:s)'),
    )
    help = 'Imports books from the specified directories.'
    args = 'directory [directory ...]'

    def handle(self, *directories, **options):
        from django.db import transaction

        self.style = color_style()

        verbose = options.get('verbose')
        force = options.get('force')
        show_traceback = options.get('traceback', False)

        wait_until = None
        if options.get('wait_until'):
            wait_until = time.mktime(time.strptime(options.get('wait_until'), '%Y-%m-%d %H:%M:%S'))
            if verbose > 0:
                print "Will wait until %s; it's %f seconds from now" % (
                    time.strftime('%Y-%m-%d %H:%M:%S', 
                    time.localtime(wait_until)), wait_until - time.time())

        # Start transaction management.
        transaction.commit_unless_managed()
        transaction.enter_transaction_management()
        transaction.managed(True)

        files_imported = 0
        files_skipped = 0

        for dir_name in directories:
            if not os.path.isdir(dir_name):
                print self.style.ERROR("%s: Not a directory. Skipping." % dir_name)
            else:
                # files queue
                files = sorted(os.listdir(dir_name))
                postponed = {}
                while files:
                    file_name = files.pop(0)
                    file_path = os.path.join(dir_name, file_name)
                    file_base, ext = os.path.splitext(file_path)

                    # Skip files that are not XML files
                    if not ext == '.xml':
                        continue

                    if verbose > 0:
                        print "Parsing '%s'" % file_path
                    else:
                        sys.stdout.write('.')
                        sys.stdout.flush()

                    # Import book files
                    try:
                        book = Book.from_xml_file(file_path, overwrite=force, 
                                                  build_epub=options.get('build_epub'),
                                                  build_txt=options.get('build_txt'),
                                                  build_pdf=options.get('build_pdf'),
                                                  build_mobi=options.get('build_mobi'))
                        files_imported += 1

                        for ebook_format in Book.ebook_formats:
                            if os.path.isfile(file_base + '.' + ebook_format):
                                getattr(book, '%s_file' % ebook_format).save(
                                    '%s.%s' % (book.slug, ebook_format), 
                                    File(file(file_base + '.' + ebook_format)))
                            if verbose:
                                print "Importing %s.%s" % (file_base, ebook_format)

                        book.save()

                    except Book.AlreadyExists, msg:
                        print self.style.ERROR('%s: Book already imported. Skipping. To overwrite use --force.' %
                            file_path)
                        files_skipped += 1

                    except Book.DoesNotExist, e:
                        if file_name not in postponed or postponed[file_name] < files_imported:
                            # push it back into the queue, maybe the missing child will show up
                            if verbose:
                                print self.style.NOTICE('Waiting for missing children')
                            files.append(file_name)
                            postponed[file_name] = files_imported
                        else:
                            # we're in a loop, nothing's being imported - some child is really missing
                            raise e

        # Print results
        print
        print "Results: %d files imported, %d skipped, %d total." % (
            files_imported, files_skipped, files_imported + files_skipped)
        print

        if wait_until:
            print 'Waiting...'
            try:
                time.sleep(wait_until - time.time())
            except IOError:
                print "it's already too late"

        transaction.commit()
        transaction.leave_transaction_management()

