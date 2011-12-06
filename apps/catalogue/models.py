# -*- coding: utf-8 -*-
# This file is part of Wolnelektury, licensed under GNU Affero GPLv3 or later.
# Copyright © Fundacja Nowoczesna Polska. See NOTICE for more information.
#
from collections import namedtuple
from datetime import datetime

from django.db import models
from django.db.models import permalink, Q
import django.dispatch
from django.core.cache import cache
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.utils.datastructures import SortedDict
from django.utils.safestring import mark_safe
from django.utils.translation import get_language
from django.core.urlresolvers import reverse
from django.db.models.signals import post_save, m2m_changed, pre_delete

from django.conf import settings

from newtagging.models import TagBase, tags_updated
from newtagging import managers
from catalogue.fields import JSONField, OverwritingFileField
from catalogue.utils import create_zip


TAG_CATEGORIES = (
    ('author', _('author')),
    ('epoch', _('epoch')),
    ('kind', _('kind')),
    ('genre', _('genre')),
    ('theme', _('theme')),
    ('set', _('set')),
    ('book', _('book')),
)


# not quite, but Django wants you to set a timeout
CACHE_FOREVER = 2419200  # 28 days


class TagSubcategoryManager(models.Manager):
    def __init__(self, subcategory):
        super(TagSubcategoryManager, self).__init__()
        self.subcategory = subcategory

    def get_query_set(self):
        return super(TagSubcategoryManager, self).get_query_set().filter(category=self.subcategory)


class Tag(TagBase):
    name = models.CharField(_('name'), max_length=50, db_index=True)
    slug = models.SlugField(_('slug'), max_length=120, db_index=True)
    sort_key = models.CharField(_('sort key'), max_length=120, db_index=True)
    category = models.CharField(_('category'), max_length=50, blank=False, null=False,
        db_index=True, choices=TAG_CATEGORIES)
    description = models.TextField(_('description'), blank=True)
    main_page = models.BooleanField(_('main page'), default=False, db_index=True, help_text=_('Show tag on main page'))

    user = models.ForeignKey(User, blank=True, null=True)
    book_count = models.IntegerField(_('book count'), blank=True, null=True)
    gazeta_link = models.CharField(blank=True, max_length=240)
    wiki_link = models.CharField(blank=True, max_length=240)

    created_at    = models.DateTimeField(_('creation date'), auto_now_add=True, db_index=True)
    changed_at    = models.DateTimeField(_('creation date'), auto_now=True, db_index=True)

    class UrlDeprecationWarning(DeprecationWarning):
        pass

    categories_rev = {
        'autor': 'author',
        'epoka': 'epoch',
        'rodzaj': 'kind',
        'gatunek': 'genre',
        'motyw': 'theme',
        'polka': 'set',
    }
    categories_dict = dict((item[::-1] for item in categories_rev.iteritems()))

    class Meta:
        ordering = ('sort_key',)
        verbose_name = _('tag')
        verbose_name_plural = _('tags')
        unique_together = (("slug", "category"),)

    def __unicode__(self):
        return self.name

    def __repr__(self):
        return "Tag(slug=%r)" % self.slug

    @permalink
    def get_absolute_url(self):
        return ('catalogue.views.tagged_object_list', [self.url_chunk])

    def has_description(self):
        return len(self.description) > 0
    has_description.short_description = _('description')
    has_description.boolean = True

    def get_count(self):
        """ returns global book count for book tags, fragment count for themes """

        if self.book_count is None:
            if self.category == 'book':
                # never used
                objects = Book.objects.none()
            elif self.category == 'theme':
                objects = Fragment.tagged.with_all((self,))
            else:
                objects = Book.tagged.with_all((self,)).order_by()
                if self.category != 'set':
                    # eliminate descendants
                    l_tags = Tag.objects.filter(slug__in=[book.book_tag_slug() for book in objects])
                    descendants_keys = [book.pk for book in Book.tagged.with_any(l_tags)]
                    if descendants_keys:
                        objects = objects.exclude(pk__in=descendants_keys)
            self.book_count = objects.count()
            self.save()
        return self.book_count

    @staticmethod
    def get_tag_list(tags):
        if isinstance(tags, basestring):
            real_tags = []
            ambiguous_slugs = []
            category = None
            deprecated = False
            tags_splitted = tags.split('/')
            for name in tags_splitted:
                if category:
                    real_tags.append(Tag.objects.get(slug=name, category=category))
                    category = None
                elif name in Tag.categories_rev:
                    category = Tag.categories_rev[name]
                else:
                    try:
                        real_tags.append(Tag.objects.exclude(category='book').get(slug=name))
                        deprecated = True 
                    except Tag.MultipleObjectsReturned, e:
                        ambiguous_slugs.append(name)

            if category:
                # something strange left off
                raise Tag.DoesNotExist()
            if ambiguous_slugs:
                # some tags should be qualified
                e = Tag.MultipleObjectsReturned()
                e.tags = real_tags
                e.ambiguous_slugs = ambiguous_slugs
                raise e
            if deprecated:
                e = Tag.UrlDeprecationWarning()
                e.tags = real_tags
                raise e
            return real_tags
        else:
            return TagBase.get_tag_list(tags)

    @property
    def url_chunk(self):
        return '/'.join((Tag.categories_dict[self.category], self.slug))


# TODO: why is this hard-coded ?
def book_upload_path(ext=None, maxlen=100):
    def get_dynamic_path(media, filename, ext=ext):
        from slughifi import slughifi

        # how to put related book's slug here?
        if not ext:
            ext = media.formats[media.type].ext
        if not media.name:
            name = slughifi(filename.split(".")[0])
        else:
            name = slughifi(media.name)
        return 'book/%s/%s.%s' % (ext, name[:maxlen-len('book/%s/.%s' % (ext, ext))-4], ext)
    return get_dynamic_path


class BookMedia(models.Model):
    FileFormat = namedtuple("FileFormat", "name ext")
    formats = SortedDict([
        ('mp3', FileFormat(name='MP3', ext='mp3')),
        ('ogg', FileFormat(name='Ogg Vorbis', ext='ogg')),
        ('daisy', FileFormat(name='DAISY', ext='daisy.zip')),
    ])
    format_choices = [(k, _('%s file') % t.name)
            for k, t in formats.items()]

    type        = models.CharField(_('type'), choices=format_choices, max_length="100")
    name        = models.CharField(_('name'), max_length="100")
    file        = OverwritingFileField(_('file'), upload_to=book_upload_path())
    uploaded_at = models.DateTimeField(_('creation date'), auto_now_add=True, editable=False)
    extra_info  = JSONField(_('extra information'), default='{}', editable=False)
    book = models.ForeignKey('Book', related_name='media')
    source_sha1 = models.CharField(null=True, blank=True, max_length=40, editable=False)


    def __unicode__(self):
        return "%s (%s)" % (self.name, self.file.name.split("/")[-1])

    class Meta:
        ordering            = ('type', 'name')
        verbose_name        = _('book media')
        verbose_name_plural = _('book media')

    def save(self, *args, **kwargs):
        from slughifi import slughifi
        from catalogue.utils import ExistingFile, remove_zip

        try:
            old = BookMedia.objects.get(pk=self.pk)
        except BookMedia.DoesNotExist, e:
            pass
        else:
            # if name changed, change the file name, too
            if slughifi(self.name) != slughifi(old.name):
                self.file.save(None, ExistingFile(self.file.path), save=False, leave=True)

        super(BookMedia, self).save(*args, **kwargs)

        # remove the zip package for book with modified media
        remove_zip(self.book.slug)

        extra_info = self.get_extra_info_value()
        extra_info.update(self.read_meta())
        self.set_extra_info_value(extra_info)
        self.source_sha1 = self.read_source_sha1(self.file.path, self.type)
        return super(BookMedia, self).save(*args, **kwargs)

    def read_meta(self):
        """
            Reads some metadata from the audiobook.
        """
        import mutagen
        from mutagen import id3

        artist_name = director_name = project = funded_by = ''
        if self.type == 'mp3':
            try:
                audio = id3.ID3(self.file.path)
                artist_name = ', '.join(', '.join(tag.text) for tag in audio.getall('TPE1'))
                director_name = ', '.join(', '.join(tag.text) for tag in audio.getall('TPE3'))
                project = ", ".join([t.data for t in audio.getall('PRIV') 
                        if t.owner=='wolnelektury.pl?project'])
                funded_by = ", ".join([t.data for t in audio.getall('PRIV') 
                        if t.owner=='wolnelektury.pl?funded_by'])
            except:
                pass
        elif self.type == 'ogg':
            try:
                audio = mutagen.File(self.file.path)
                artist_name = ', '.join(audio.get('artist', []))
                director_name = ', '.join(audio.get('conductor', []))
                project = ", ".join(audio.get('project', []))
                funded_by = ", ".join(audio.get('funded_by', []))
            except:
                pass
        else:
            return {}
        return {'artist_name': artist_name, 'director_name': director_name,
                'project': project, 'funded_by': funded_by}

    @staticmethod
    def read_source_sha1(filepath, filetype):
        """
            Reads source file SHA1 from audiobok metadata.
        """
        import mutagen
        from mutagen import id3

        if filetype == 'mp3':
            try:
                audio = id3.ID3(filepath)
                return [t.data for t in audio.getall('PRIV') 
                        if t.owner=='wolnelektury.pl?flac_sha1'][0]
            except:
                return None
        elif filetype == 'ogg':
            try:
                audio = mutagen.File(filepath)
                return audio.get('flac_sha1', [None])[0] 
            except:
                return None
        else:
            return None


class Book(models.Model):
    title         = models.CharField(_('title'), max_length=120)
    sort_key = models.CharField(_('sort key'), max_length=120, db_index=True, editable=False)
    slug          = models.SlugField(_('slug'), max_length=120, unique=True, db_index=True)
    description   = models.TextField(_('description'), blank=True)
    created_at    = models.DateTimeField(_('creation date'), auto_now_add=True, db_index=True)
    changed_at    = models.DateTimeField(_('creation date'), auto_now=True, db_index=True)
    parent_number = models.IntegerField(_('parent number'), default=0)
    extra_info    = JSONField(_('extra information'), default='{}')
    gazeta_link   = models.CharField(blank=True, max_length=240)
    wiki_link     = models.CharField(blank=True, max_length=240)
    # files generated during publication

    ebook_formats = ['pdf', 'epub', 'mobi', 'txt']
    formats = ebook_formats + ['html', 'xml']

    parent        = models.ForeignKey('self', blank=True, null=True, related_name='children')
    objects  = models.Manager()
    tagged   = managers.ModelTaggedItemManager(Tag)
    tags     = managers.TagDescriptor(Tag)

    html_built = django.dispatch.Signal()
    published = django.dispatch.Signal()

    class AlreadyExists(Exception):
        pass

    class Meta:
        ordering = ('sort_key',)
        verbose_name = _('book')
        verbose_name_plural = _('books')

    def __unicode__(self):
        return self.title

    def save(self, force_insert=False, force_update=False, reset_short_html=True, **kwargs):
        from sortify import sortify

        self.sort_key = sortify(self.title)

        ret = super(Book, self).save(force_insert, force_update)

        if reset_short_html:
            self.reset_short_html()

        return ret

    @permalink
    def get_absolute_url(self):
        return ('catalogue.views.book_detail', [self.slug])

    @property
    def name(self):
        return self.title

    def book_tag_slug(self):
        return ('l-' + self.slug)[:120]

    def book_tag(self):
        slug = self.book_tag_slug()
        book_tag, created = Tag.objects.get_or_create(slug=slug, category='book')
        if created:
            book_tag.name = self.title[:50]
            book_tag.sort_key = self.title.lower()
            book_tag.save()
        return book_tag

    def has_media(self, type):
        if type in Book.formats:
            return bool(getattr(self, "%s_file" % type))
        else:
            return self.media.filter(type=type).exists()

    def get_media(self, type):
        if self.has_media(type):
            if type in Book.formats:
                return getattr(self, "%s_file" % type)
            else:                                             
                return self.media.filter(type=type)
        else:
            return None

    def get_mp3(self):
        return self.get_media("mp3")
    def get_odt(self):
        return self.get_media("odt")
    def get_ogg(self):
        return self.get_media("ogg")
    def get_daisy(self):
        return self.get_media("daisy")                       

    def reset_short_html(self):
        if self.id is None:
            return

        cache_key = "Book.short_html/%d/%s"
        for lang, langname in settings.LANGUAGES:
            cache.delete(cache_key % (self.id, lang))
        # Fragment.short_html relies on book's tags, so reset it here too
        for fragm in self.fragments.all():
            fragm.reset_short_html()

    def short_html(self):
        if self.id:
            cache_key = "Book.short_html/%d/%s" % (self.id, get_language())
            short_html = cache.get(cache_key)
        else:
            short_html = None

        if short_html is not None:
            return mark_safe(short_html)
        else:
            tags = self.tags.filter(~Q(category__in=('set', 'theme', 'book')))
            tags = [mark_safe(u'<a href="%s">%s</a>' % (tag.get_absolute_url(), tag.name)) for tag in tags]

            formats = []
            # files generated during publication
            if self.has_media("html"):
                formats.append(u'<a href="%s">%s</a>' % (reverse('book_text', kwargs={'slug': self.slug}), _('Read online')))
            for ebook_format in self.ebook_formats:
                if self.has_media(ebook_format):
                    formats.append(u'<a href="%s">%s</a>' % (
                        self.get_media(ebook_format).url,
                        ebook_format.upper()
                        ))
            # other files
            for m in self.media.order_by('type'):
                formats.append(u'<a href="%s">%s</a>' % (m.file.url, m.type.upper()))

            formats = [mark_safe(format) for format in formats]

            short_html = unicode(render_to_string('catalogue/book_short.html',
                {'book': self, 'tags': tags, 'formats': formats}))

            if self.id:
                cache.set(cache_key, short_html, CACHE_FOREVER)
            return mark_safe(short_html)

    def has_description(self):
        return len(self.description) > 0
    has_description.short_description = _('description')
    has_description.boolean = True

    # ugly ugly ugly
    def has_mp3_file(self):
        return bool(self.has_media("mp3"))
    has_mp3_file.short_description = 'MP3'
    has_mp3_file.boolean = True

    def has_ogg_file(self):
        return bool(self.has_media("ogg"))
    has_ogg_file.short_description = 'OGG'
    has_ogg_file.boolean = True

    def has_daisy_file(self):
        return bool(self.has_media("daisy"))
    has_daisy_file.short_description = 'DAISY'
    has_daisy_file.boolean = True

    def build_pdf(self):
        """ (Re)builds the pdf file.

        """
        from tempfile import NamedTemporaryFile
        from os import unlink
        from django.core.files import File
        from librarian import pdf
        from catalogue.utils import ORMDocProvider, remove_zip

        try:
            pdf_file = NamedTemporaryFile(delete=False)
            pdf.transform(ORMDocProvider(self),
                      file_path=str(self.xml_file.path),
                      output_file=pdf_file,
                      )

            self.pdf_file.save('%s.pdf' % self.slug, File(open(pdf_file.name)))
        finally:
            unlink(pdf_file.name)

        # remove zip with all pdf files
        remove_zip(settings.ALL_PDF_ZIP)

    def build_mobi(self):
        """ (Re)builds the MOBI file.

        """
        from tempfile import NamedTemporaryFile
        from os import unlink
        from django.core.files import File
        from librarian import mobi
        from catalogue.utils import ORMDocProvider, remove_zip

        try:
            mobi_file = NamedTemporaryFile(suffix='.mobi', delete=False)
            mobi.transform(ORMDocProvider(self), verbose=1,
                      file_path=str(self.xml_file.path),
                      output_file=mobi_file.name,
                      )

            self.mobi_file.save('%s.mobi' % self.slug, File(open(mobi_file.name)))
        finally:
            unlink(mobi_file.name)

        # remove zip with all mobi files
        remove_zip(settings.ALL_MOBI_ZIP)

    def build_epub(self):
        """(Re)builds the epub file."""
        from StringIO import StringIO
        from hashlib import sha1
        from django.core.files.base import ContentFile
        from librarian import epub, NoDublinCore
        from catalogue.utils import ORMDocProvider, remove_zip

        epub_file = StringIO()
        try:
            epub.transform(ORMDocProvider(self), self.slug, output_file=epub_file)
            self.epub_file.save('%s.epub' % self.slug, ContentFile(epub_file.getvalue()))
            FileRecord(slug=self.slug, type='epub', sha1=sha1(epub_file.getvalue()).hexdigest()).save()
        except NoDublinCore:
            pass

        # remove zip package with all epub files
        remove_zip(settings.ALL_EPUB_ZIP)

    def build_txt(self):
        from StringIO import StringIO
        from django.core.files.base import ContentFile
        from librarian import text

        out = StringIO()
        text.transform(open(self.xml_file.path), out)
        self.txt_file.save('%s.txt' % self.slug, ContentFile(out.getvalue()))


    def build_html(self):
        from tempfile import NamedTemporaryFile
        from markupstring import MarkupString
        from django.core.files import File
        from slughifi import slughifi
        from librarian import html

        meta_tags = list(self.tags.filter(
            category__in=('author', 'epoch', 'genre', 'kind')))
        book_tag = self.book_tag()

        html_file = NamedTemporaryFile()
        if html.transform(self.xml_file.path, html_file, parse_dublincore=False):
            self.html_file.save('%s.html' % self.slug, File(html_file))

            # get ancestor l-tags for adding to new fragments
            ancestor_tags = []
            p = self.parent
            while p:
                ancestor_tags.append(p.book_tag())
                p = p.parent

            # Delete old fragments and create them from scratch
            self.fragments.all().delete()
            # Extract fragments
            closed_fragments, open_fragments = html.extract_fragments(self.html_file.path)
            for fragment in closed_fragments.values():
                try:
                    theme_names = [s.strip() for s in fragment.themes.split(',')]
                except AttributeError:
                    continue
                themes = []
                for theme_name in theme_names:
                    if not theme_name:
                        continue
                    tag, created = Tag.objects.get_or_create(slug=slughifi(theme_name), category='theme')
                    if created:
                        tag.name = theme_name
                        tag.sort_key = theme_name.lower()
                        tag.save()
                    themes.append(tag)
                if not themes:
                    continue

                text = fragment.to_string()
                short_text = ''
                if (len(MarkupString(text)) > 240):
                    short_text = unicode(MarkupString(text)[:160])
                new_fragment = Fragment.objects.create(anchor=fragment.id, book=self,
                    text=text, short_text=short_text)

                new_fragment.save()
                new_fragment.tags = set(meta_tags + themes + [book_tag] + ancestor_tags)
            self.save()
            self.html_built.send(sender=self)
            return True
        return False

    @staticmethod
    def zip_format(format_):
        def pretty_file_name(book):
            return "%s/%s.%s" % (
                b.get_extra_info_value()['author'],
                b.slug,
                format_)

        field_name = "%s_file" % format_
        books = Book.objects.filter(parent=None).exclude(**{field_name: ""})
        paths = [(pretty_file_name(b), getattr(b, field_name).path)
                    for b in books]
        result = create_zip.delay(paths,
                    getattr(settings, "ALL_%s_ZIP" % format_.upper()))
        return result.wait()

    def zip_audiobooks(self):
        bm = BookMedia.objects.filter(book=self, type='mp3')
        paths = map(lambda bm: (None, bm.file.path), bm)
        result = create_zip.delay(paths, self.slug)
        return result.wait()

    @classmethod
    def from_xml_file(cls, xml_file, **kwargs):
        from django.core.files import File
        from librarian import dcparser

        # use librarian to parse meta-data
        book_info = dcparser.parse(xml_file)

        if not isinstance(xml_file, File):
            xml_file = File(open(xml_file))

        try:
            return cls.from_text_and_meta(xml_file, book_info, **kwargs)
        finally:
            xml_file.close()

    @classmethod
    def from_text_and_meta(cls, raw_file, book_info, overwrite=False,
            build_epub=True, build_txt=True, build_pdf=True, build_mobi=True):
        import re
        from slughifi import slughifi
        from sortify import sortify

        # check for parts before we do anything
        children = []
        if hasattr(book_info, 'parts'):
            for part_url in book_info.parts:
                base, slug = part_url.rsplit('/', 1)
                try:
                    children.append(Book.objects.get(slug=slug))
                except Book.DoesNotExist, e:
                    raise Book.DoesNotExist(_('Book with slug = "%s" does not exist.') % slug)


        # Read book metadata
        book_base, book_slug = book_info.url.rsplit('/', 1)
        if re.search(r'[^a-zA-Z0-9-]', book_slug):
            raise ValueError('Invalid characters in slug')
        book, created = Book.objects.get_or_create(slug=book_slug)

        if created:
            book_shelves = []
        else:
            if not overwrite:
                raise Book.AlreadyExists(_('Book %s already exists') % book_slug)
            # Save shelves for this book
            book_shelves = list(book.tags.filter(category='set'))

        book.title = book_info.title
        book.set_extra_info_value(book_info.to_dict())
        book.save()

        meta_tags = []
        categories = (('kinds', 'kind'), ('genres', 'genre'), ('authors', 'author'), ('epochs', 'epoch'))
        for field_name, category in categories:
            try:
                tag_names = getattr(book_info, field_name)
            except:
                tag_names = [getattr(book_info, category)]
            for tag_name in tag_names:
                tag_sort_key = tag_name
                if category == 'author':
                    tag_sort_key = tag_name.last_name
                    tag_name = ' '.join(tag_name.first_names) + ' ' + tag_name.last_name
                tag, created = Tag.objects.get_or_create(slug=slughifi(tag_name), category=category)
                if created:
                    tag.name = tag_name
                    tag.sort_key = sortify(tag_sort_key.lower())
                    tag.save()
                meta_tags.append(tag)

        book.tags = set(meta_tags + book_shelves)

        book_tag = book.book_tag()

        for n, child_book in enumerate(children):
            child_book.parent = book
            child_book.parent_number = n
            child_book.save()

        # Save XML and HTML files
        book.xml_file.save('%s.xml' % book.slug, raw_file, save=False)

        # delete old fragments when overwriting
        book.fragments.all().delete()

        if book.build_html():
            if not settings.NO_BUILD_TXT and build_txt:
                book.build_txt()

        if not settings.NO_BUILD_EPUB and build_epub:
            book.build_epub()

        if not settings.NO_BUILD_PDF and build_pdf:
            book.build_pdf()

        if not settings.NO_BUILD_MOBI and build_mobi:
            book.build_mobi()

        book_descendants = list(book.children.all())
        # add l-tag to descendants and their fragments
        while len(book_descendants) > 0:
            child_book = book_descendants.pop(0)
            child_book.tags = list(child_book.tags) + [book_tag]
            child_book.save()
            for fragment in child_book.fragments.all():
                fragment.tags = set(list(fragment.tags) + [book_tag])
            book_descendants += list(child_book.children.all())

        book.save()

        # refresh cache
        book.reset_tag_counter()
        book.reset_theme_counter()

        cls.published.send(sender=book)
        return book

    def reset_tag_counter(self):
        if self.id is None:
            return

        cache_key = "Book.tag_counter/%d" % self.id
        cache.delete(cache_key)
        if self.parent:
            self.parent.reset_tag_counter()

    @property
    def tag_counter(self):
        if self.id:
            cache_key = "Book.tag_counter/%d" % self.id
            tags = cache.get(cache_key)
        else:
            tags = None

        if tags is None:
            tags = {}
            for child in self.children.all().order_by():
                for tag_pk, value in child.tag_counter.iteritems():
                    tags[tag_pk] = tags.get(tag_pk, 0) + value
            for tag in self.tags.exclude(category__in=('book', 'theme', 'set')).order_by():
                tags[tag.pk] = 1

            if self.id:
                cache.set(cache_key, tags, CACHE_FOREVER)
        return tags

    def reset_theme_counter(self):
        if self.id is None:
            return

        cache_key = "Book.theme_counter/%d" % self.id
        cache.delete(cache_key)
        if self.parent:
            self.parent.reset_theme_counter()

    @property
    def theme_counter(self):
        if self.id:
            cache_key = "Book.theme_counter/%d" % self.id
            tags = cache.get(cache_key)
        else:
            tags = None

        if tags is None:
            tags = {}
            for fragment in Fragment.tagged.with_any([self.book_tag()]).order_by():
                for tag in fragment.tags.filter(category='theme').order_by():
                    tags[tag.pk] = tags.get(tag.pk, 0) + 1

            if self.id:
                cache.set(cache_key, tags, CACHE_FOREVER)
        return tags

    def pretty_title(self, html_links=False):
        book = self
        names = list(book.tags.filter(category='author'))

        books = []
        while book:
            books.append(book)
            book = book.parent
        names.extend(reversed(books))

        if html_links:
            names = ['<a href="%s">%s</a>' % (tag.get_absolute_url(), tag.name) for tag in names]
        else:
            names = [tag.name for tag in names]

        return ', '.join(names)

    @classmethod
    def tagged_top_level(cls, tags):
        """ Returns top-level books tagged with `tags'.

        It only returns those books which don't have ancestors which are
        also tagged with those tags.

        """
        # get relevant books and their tags
        objects = cls.tagged.with_all(tags)
        # eliminate descendants
        l_tags = Tag.objects.filter(category='book', slug__in=[book.book_tag_slug() for book in objects])
        descendants_keys = [book.pk for book in cls.tagged.with_any(l_tags)]
        if descendants_keys:
            objects = objects.exclude(pk__in=descendants_keys)

        return objects

    @classmethod
    def book_list(cls, filter=None):
        """Generates a hierarchical listing of all books.

        Books are optionally filtered with a test function.

        """

        books_by_parent = {}
        books = cls.objects.all().order_by('parent_number', 'sort_key').only('title', 'parent', 'slug')
        if filter:
            books = books.filter(filter).distinct()
            book_ids = set((book.pk for book in books))
            for book in books:
                parent = book.parent_id
                if parent not in book_ids:
                    parent = None
                books_by_parent.setdefault(parent, []).append(book)
        else:
            for book in books:
                books_by_parent.setdefault(book.parent_id, []).append(book)

        orphans = []
        books_by_author = SortedDict()
        for tag in Tag.objects.filter(category='author'):
            books_by_author[tag] = []

        for book in books_by_parent.get(None,()):
            authors = list(book.tags.filter(category='author'))
            if authors:
                for author in authors:
                    books_by_author[author].append(book)
            else:
                orphans.append(book)

        return books_by_author, orphans, books_by_parent

    _audiences_pl = {
        "SP1": (1, u"szkoła podstawowa"),
        "SP2": (1, u"szkoła podstawowa"),
        "P": (1, u"szkoła podstawowa"),
        "G": (2, u"gimnazjum"),
        "L": (3, u"liceum"),
        "LP": (3, u"liceum"),
    }
    def audiences_pl(self):
        audiences = self.get_extra_info_value().get('audiences', [])
        audiences = sorted(set([self._audiences_pl[a] for a in audiences]))
        return [a[1] for a in audiences]


def _has_factory(ftype):
    has = lambda self: bool(getattr(self, "%s_file" % ftype))
    has.short_description = t.upper()
    has.boolean = True
    has.__name__ = "has_%s_file" % ftype
    return has

    
# add the file fields
for t in Book.formats:
    field_name = "%s_file" % t
    models.FileField(_("%s file" % t.upper()),
            upload_to=book_upload_path(t),
            blank=True).contribute_to_class(Book, field_name)

    setattr(Book, "has_%s_file" % t, _has_factory(t))


class Fragment(models.Model):
    text = models.TextField()
    short_text = models.TextField(editable=False)
    anchor = models.CharField(max_length=120)
    book = models.ForeignKey(Book, related_name='fragments')

    objects = models.Manager()
    tagged = managers.ModelTaggedItemManager(Tag)
    tags = managers.TagDescriptor(Tag)

    class Meta:
        ordering = ('book', 'anchor',)
        verbose_name = _('fragment')
        verbose_name_plural = _('fragments')

    def get_absolute_url(self):
        return '%s#m%s' % (reverse('book_text', kwargs={'slug': self.book.slug}), self.anchor)

    def reset_short_html(self):
        if self.id is None:
            return

        cache_key = "Fragment.short_html/%d/%s"
        for lang, langname in settings.LANGUAGES:
            cache.delete(cache_key % (self.id, lang))

    def short_html(self):
        if self.id:
            cache_key = "Fragment.short_html/%d/%s" % (self.id, get_language())
            short_html = cache.get(cache_key)
        else:
            short_html = None

        if short_html is not None:
            return mark_safe(short_html)
        else:
            short_html = unicode(render_to_string('catalogue/fragment_short.html',
                {'fragment': self}))
            if self.id:
                cache.set(cache_key, short_html, CACHE_FOREVER)
            return mark_safe(short_html)


class FileRecord(models.Model):
    slug = models.SlugField(_('slug'), max_length=120, db_index=True)
    type = models.CharField(_('type'), max_length=20, db_index=True)
    sha1 = models.CharField(_('sha-1 hash'), max_length=40)
    time = models.DateTimeField(_('time'), auto_now_add=True)

    class Meta:
        ordering = ('-time','-slug', '-type')
        verbose_name = _('file record')
        verbose_name_plural = _('file records')

    def __unicode__(self):
        return "%s %s.%s" % (self.sha1,  self.slug, self.type)

###########
#
# SIGNALS
#
###########


def _tags_updated_handler(sender, affected_tags, **kwargs):
    # reset tag global counter
    # we want Tag.changed_at updated for API to know the tag was touched
    Tag.objects.filter(pk__in=[tag.pk for tag in affected_tags]).update(book_count=None, changed_at=datetime.now())

    # if book tags changed, reset book tag counter
    if isinstance(sender, Book) and \
                Tag.objects.filter(pk__in=(tag.pk for tag in affected_tags)).\
                    exclude(category__in=('book', 'theme', 'set')).count():
        sender.reset_tag_counter()
    # if fragment theme changed, reset book theme counter
    elif isinstance(sender, Fragment) and \
                Tag.objects.filter(pk__in=(tag.pk for tag in affected_tags)).\
                    filter(category='theme').count():
        sender.book.reset_theme_counter()
tags_updated.connect(_tags_updated_handler)


def _pre_delete_handler(sender, instance, **kwargs):
    """ refresh Book on BookMedia delete """
    if sender == BookMedia:
        instance.book.save()
pre_delete.connect(_pre_delete_handler)

def _post_save_handler(sender, instance, **kwargs):
    """ refresh all the short_html stuff on BookMedia update """
    if sender == BookMedia:
        instance.book.save()
post_save.connect(_post_save_handler)
